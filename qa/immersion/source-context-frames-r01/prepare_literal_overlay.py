from pathlib import Path
import hashlib,json,subprocess,shutil
R=Path(__file__).resolve().parents[3];W=Path('/home/ai/Development/investigations/vipi-source-context-frames-20261109-r01/native-literal-overlay-r01');W.mkdir(exist_ok=False)
paths={'kt':'android/core/src/main/kotlin/co/fallsoft/vipi/core/TranslationIntegrity.kt','swift':'ios/VipiCore/Sources/VipiCore/TranslationIntegrity.swift'};out={}
for ext,path in paths.items():
 raw=subprocess.check_output(['git','show','HEAD:'+path],cwd=R).decode()
 if ext=='kt':
  start=raw.index('        var value = match.value');end=raw.index('        value\n',start);body=raw[start:end]
  extra='    /** Private QA range view of the same matcher and URL trimming; no predicate change. */\n    fun qaLiteralRanges(text: String): List<IntRange> = literals.findAll(text).mapNotNull { match ->\n'+body+'        if (value.isEmpty()) null else match.range.first until (match.range.first + value.length)\n    }.toList()\n\n'
  marker='    fun preservesIdentifiers'
 else:
  start=raw.index('            var value = ns.substring(with: match.range)');end=raw.index('\n            ',start+20)
  # Exact retained trim block ends immediately before append(value).
  end=raw.index('            values.append',start) if '            values.append' in raw[start:] else raw.index('            result.append',start)
  body=raw[start:end]
  extra='    /// Private QA range view of the same matcher and URL trimming; no predicate change.\n    public static func qaLiteralRanges(_ text:String) -> [NSRange] {\n        let ns=text as NSString;var result:[NSRange]=[]\n        for match in literals.matches(in:text,range:NSRange(location:0,length:ns.length)) {\n'+body+'            if !value.isEmpty { result.append(NSRange(location:match.range.location,length:value.utf16.count)) }\n        }\n        return result\n    }\n\n'
  marker='    public static func preservesIdentifiers'
 assert marker in raw
 final=raw.replace(marker,extra+marker,1);assert final.replace(extra,'',1)==raw
 p=W/('TranslationIntegrity.'+ext);p.write_text(final);out[path]={'original_sha256':hashlib.sha256(raw.encode()).hexdigest(),'overlay_sha256':hashlib.sha256(final.encode()).hexdigest(),'original_bytes_reconstructed':True}
(W/'receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(out)
