#!/usr/bin/env python3
"""Fixed multilingual token-alignment probe; no application integration.

This evaluates correspondence between authored parallel sentences, not whether
machine translation is faithful or whether a replacement has correct grammar.
It uses mutual nearest-neighbour cosine alignment with native word boundaries.
E5 is an experimental adaptation; mBERT layer 8 follows SimAlign's model choice.
Neither configuration reproduces their published benchmark or token boundaries.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import time

import numpy as np
from tokenizers import Tokenizer

GOLD = {
    "coffee_plan": {
        "coffee": dict(en="Coffee", es="café", fr="café", de="Kaffee", it="caffè", pt="café", ar="القهوة", zh="咖啡", ja="コーヒー", ko="커피"),
        "tomorrow": dict(en="tomorrow", es="mañana", fr="demain", de="Morgen", it="domani", pt="amanhã", ar="غدًا", zh="明天", ja="明日", ko="내일"),
    },
    "bank_finance": {
        "bank": dict(en="bank", es="banco", fr="banque", de="Bank", it="banca", pt="banco", ar="بنك", zh="银行", ja="銀行", ko="은행"),
        "account": dict(en="account", es="cuenta", fr="compte", de="Konto", it="conto", pt="conta", ar="حساب", zh="账户", ja="口座", ko="계좌"),
    },
}


def main(args):
    args.output.mkdir(parents=True, exist_ok=False)
    corpus = json.loads(args.corpus.read_text())
    native = json.loads(args.native.read_text())
    texts = {c["id"]: c["text"] for c in corpus["cases"] if c["id"] in GOLD}
    words = {}
    for pair in native["results"]:
        for sample in pair["samples"]:
            if sample["id"] in GOLD:
                key = (sample["id"], pair["source"])
                assert sample["original"] == texts[key[0]][key[1]]
                assert all(sample["original"][w["start"]:w["end"]] == w["text"] for w in sample["source_words"]), "Unexpected UTF-16/code-point offset difference"
                if key in words:
                    assert words[key] == sample["source_words"]
                words[key] = sample["source_words"]
    prefix = "query: " if args.backend == "e5" else ""
    model_files = [args.model / p for p in (["onnx/model_qint8_avx512_vnni.onnx", "onnx/tokenizer.json"] if args.backend == "e5" else ["model.safetensors", "tokenizer.json", "config.json"])]
    protocol = {"schema": 2, "backend": args.backend, "gold": GOLD, "prefix": prefix, "pool": "mean of overlapping contextual subword vectors per existing native word, then L2",
                "selection": "mutual top-one cosine; no threshold fitted", "criterion": "selected native target word overlaps the authored gold substring; does not qualify exact replacement span",
                "scope": "360 easy authored correspondences, 90 directions, two scenarios; development probe, not untouched acceptance",
                "source_hashes": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.corpus, args.native, *model_files]},
                "method_reference": "https://aclanthology.org/2020.findings-emnlp.147/"}
    raw = (json.dumps(protocol, ensure_ascii=False, indent=2) + "\n").encode()
    (args.output / "protocol.json").write_bytes(raw)
    tokenizer = Tokenizer.from_file(str(args.model / ("onnx/tokenizer.json" if args.backend == "e5" else "tokenizer.json")))
    tokenizer.no_truncation(); tokenizer.no_padding()
    start = time.perf_counter()
    if args.backend == "e5":
        import onnxruntime as ort
        opts = ort.SessionOptions(); opts.intra_op_num_threads = 2; opts.inter_op_num_threads = 1
        session = ort.InferenceSession(str(model_files[0]), sess_options=opts, providers=["CPUExecutionProvider"])
        names = {i.name for i in session.get_inputs()}
        def encode(feed):
            return session.run(None, {k:v for k,v in feed.items() if k in names})[0][0]
    else:
        import torch
        from transformers import BertModel
        torch.set_num_threads(2); torch.set_num_interop_threads(1)
        model = BertModel.from_pretrained(args.model, local_files_only=True, use_safetensors=True,
                                          output_hidden_states=True, attn_implementation="eager").eval()
        def encode(feed):
            with torch.inference_mode():
                return model(**{k:torch.from_numpy(v) for k,v in feed.items()}).hidden_states[8][0].numpy()
    load_ms = (time.perf_counter()-start)*1000
    vectors = {}; timings = []
    for key, native_words in words.items():
        start = time.perf_counter()
        text = protocol["prefix"] + texts[key[0]][key[1]]
        encoding = tokenizer.encode(text)
        assert len(encoding.ids) <= 512
        feed = {"input_ids": np.array([encoding.ids], dtype=np.int64), "attention_mask": np.array([encoding.attention_mask], dtype=np.int64), "token_type_ids": np.array([encoding.type_ids], dtype=np.int64)}
        embeddings = encode(feed)
        pooled = []
        for word in native_words:
            indices = [i for i,(a,b) in enumerate(encoding.offsets) if not encoding.special_tokens_mask[i] and a < word["end"]+len(prefix) and b > word["start"]+len(prefix)]
            assert indices, (key,word)
            vector = embeddings[indices].mean(axis=0)
            pooled.append(vector / np.linalg.norm(vector))
        vectors[key] = np.array(pooled)
        timings.append((time.perf_counter()-start)*1000)

    def gold_indices(case, concept, lang):
        sentence = texts[case][lang]; term = GOLD[case][concept][lang]
        assert sentence.count(term) == 1, (case, concept, lang)
        start = sentence.index(term); end = start+len(term)
        return [i for i,w in enumerate(words[(case,lang)]) if w["start"] < end and w["end"] > start]

    observations = []
    for case, concepts in GOLD.items():
        for src in corpus["languages"]:
            for dst in corpus["languages"]:
                if src == dst: continue
                sims = vectors[case,src] @ vectors[case,dst].T
                for concept in concepts:
                    source_ids = gold_indices(case,concept,src); target_ids = gold_indices(case,concept,dst)
                    # Multi-token gold remains visible as a limitation; no silent averaging change.
                    assert len(source_ids) == 1 and len(target_ids) == 1, (case,concept,src,dst,source_ids,target_ids)
                    i = source_ids[0]; j = int(sims[i].argmax()); mutual = int(sims[:,j].argmax()) == i
                    observations.append({"case":case,"concept":concept,"source":src,"target":dst,
                        "source_word":words[case,src][i]["text"],"expected_target":words[case,dst][target_ids[0]]["text"],
                        "top_target":words[case,dst][j]["text"],"cosine":float(sims[i,j]),"mutual":mutual,
                        "top_correct":j in target_ids,"accepted_correct":mutual and j in target_ids})
    report = {"protocol_sha256":hashlib.sha256(raw).hexdigest(),"cases":len(observations),"top_correct":sum(o["top_correct"] for o in observations),
              "selected":sum(o["mutual"] for o in observations),"selected_wrong":sum(o["mutual"] and not o["top_correct"] for o in observations),
              "load_ms":load_ms,"sentence_p50_ms":float(np.median(timings)),"sentence_p95_ms":float(np.percentile(timings,95)),
              "peak_rss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,"platform":"OZZZ-OS x86 CPU, two threads; not mobile",
              "linguistic_acceptance":False,"translation_faithfulness_tested":False,"observations":observations}
    (args.output / "report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k != "observations"},indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["e5", "mbert-layer8"], default="e5")
    for name in ["corpus","native","model","output"]: parser.add_argument("--"+name,type=Path,required=True)
    main(parser.parse_args())
