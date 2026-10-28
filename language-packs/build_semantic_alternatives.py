#!/usr/bin/env python3
"""Experimental context alternatives sharing explicit dictionary links.

Counts concern compatible published relations, not calibrated semantic accuracy.
All observations, including unknown/competing counterparts, remain in the denominator.
No translation, spelling, reading, or runtime grammar is generated.
"""
import argparse,hashlib,itertools,json,shutil,sqlite3,time
from collections import defaultdict,Counter
from contextlib import closing
from functools import lru_cache
from pathlib import Path
from build_wiktextract import canonical,digest_file
POLICY="shared-explicit-verb-alternatives-1"
NOUN_POLICY="shared-explicit-noun-alternatives-1"

class NounRelations:
    """Whole surface forms only; no stem, spelling or relation generation."""
    def __init__(self,db):
        grouped=defaultdict(set)
        for head,sense in db.execute("""SELECT l.normalized,t.sense
            FROM lexemes l JOIN terms t ON t.lexeme=l.id JOIN senses s ON s.id=t.sense
            WHERE l.pos='noun' AND l.target_safe=1 AND t.eligible=1 AND s.explicit=1"""):
            grouped[head].add(sense)
        self.relations={head:frozenset(senses) for head,senses in grouped.items()}
        self.db=db
    @lru_cache(maxsize=100000)
    def heads(self,word):
        if word.startswith("@"):return ()
        heads=set()
        for head,written,start,end in self.db.execute("""SELECT l.normalized,f.surface,f.start,f.end
            FROM surfaces f JOIN lexemes l ON l.id=f.lexeme
            WHERE f.normalized=? AND l.pos='noun' AND l.target_safe=1 AND f.mode IN (1,2)""",(word,)):
            if start==0 and end==len(written.encode("utf-16-le"))//2 and head in self.relations:heads.add(head)
        return tuple((head,self.relations[head]) for head in sorted(heads))
    def source_relations(self,word):
        heads=self.heads(word)
        # Same-spelling heads from different noun lemmas remain unresolved.
        return heads[0][1] if len(heads)==1 else frozenset()

def qualify(rows,minimum=3,agreement=.98):
    """One source sentence is one vote; conflicting aliases veto that vote."""
    sentences={}
    for sentence,translation,head,senses in rows:
        if sentence not in sentences:sentences[sentence]=[set(senses),defaultdict(set)]
        else:sentences[sentence][0].intersection_update(senses)
        if head:sentences[sentence][1][head].add(translation)
    total=len(sentences);by_sense=defaultdict(set);by_head=defaultdict(set)
    for sentence,(senses,heads) in sentences.items():
        for sense in senses:by_sense[sense].add(sentence)
        for head in heads:by_head[head].add(sentence)
    output=[]
    for head,head_refs in by_head.items():
        choices=[]
        for sense,refs in by_sense.items():
            counterpart=refs & head_refs
            if len(refs)>=minimum and len(refs)/total>=agreement and len(counterpart)>=minimum:
                choices.append((len(refs),len(counterpart),sense,refs,counterpart))
        if not choices:continue
        # Preserve alternative compatible relations; do not assert a label is
        # the contextual meaning. Each returned relation meets both thresholds.
        best=max((n,k) for n,k,_,_,_ in choices)
        selected=[r for r in choices if r[:2]==best]
        # Count fields have a concrete witness set. Multiple sense relations
        # with different vote sets are not unioned to manufacture agreement.
        signature=min(tuple(sorted(r[3])) for r in selected)
        selected=[r for r in selected if tuple(sorted(r[3]))==signature]
        senses=sorted(r[2] for r in selected);refs=set(signature)
        actual=refs & head_refs
        evidence=[(sid,min(sentences[sid][1][head])) for sid in sorted(actual)[:3]]
        output.append(dict(head=head,support=len(refs),total=total,counterpart_support=len(actual),
            candidate_senses=senses,evidence=evidence))
    return output

def build(args):
    started=time.monotonic()
    observed=json.loads(args.observations.with_name("receipt.json").read_text())
    kind=getattr(args,"kind","present");noun=kind=="noun"
    assert kind in ("present","noun") and observed["complete"]
    if noun:
        assert observed["schema"]=="vipi-filtered-context-observations-1"
        assert observed["source_filter_policy"]=="complete-explicit-noun-spellings-1"
        assert observed["alignment_kind"]==0 and observed["all_matching_legacy_competing_targets_retained"]
    else:assert observed["exact_present_subset"] and observed["all_present_competing_targets_retained"]
    assert digest_file(args.observations)==observed["sha256"]
    catalog=json.loads(args.dictionary.read_text())
    if noun:
        assert observed["source_release_id"]==catalog["release_id"]
        assert observed["source_catalog_sha256"]==digest_file(args.dictionary)
    table="noun_semantic_alternatives" if noun else "semantic_alternatives"
    examples_table="noun_semantic_alternative_examples" if noun else "semantic_alternative_examples"
    meta_prefix="noun_semantic_alternative" if noun else "semantic_alternative"
    policy=NOUN_POLICY if noun else POLICY
    base_pin=json.loads(args.base.with_name("receipt.json").read_text())
    assert base_pin["complete"] and digest_file(args.base)==base_pin["sha256"]
    args.output.mkdir(exist_ok=False,parents=True)
    target=args.output/"witnesses.sqlite";shutil.copyfile(args.base,target)
    dictionaries={};counts=Counter()
    try:
        for row in catalog["shards"]:
            if row["language"] not in set(args.languages):continue
            p=args.dictionary.parent/(row["language"]+".sqlite")
            assert digest_file(p)==row["sha256"]
            dictionaries[row["language"]]=sqlite3.connect(p.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
        # The original query scanned all terms for every uncached head.
        # Materialize the same explicit relations once per selected dictionary.
        head_relations={}
        for language,db in dictionaries.items():
            grouped=defaultdict(set)
            for head,sense in db.execute("""SELECT l.normalized,t.sense
                FROM lexemes l JOIN terms t ON t.lexeme=l.id JOIN senses s ON s.id=t.sense
                WHERE l.pos='verb' AND l.target_safe=1 AND t.eligible=1 AND s.explicit=1"""):
                grouped[head].add(sense)
            head_relations[language]={head:frozenset(senses) for head,senses in grouped.items()}
        def source_relations(language,word):
            assert word.startswith("@present:")
            return head_relations[language].get(word[len("@present:"):],frozenset())
        @lru_cache(maxsize=100000)
        def target_relations(language,word):
            relations=head_relations[language]
            if word.startswith(("@present:","@past:")):
                head=word.split(":",1)[1]
                return ((head,relations[head]),) if head in relations else ()
            heads={r[0] for r in dictionaries[language].execute("""SELECT DISTINCT l.normalized
                FROM surfaces f JOIN lexemes l ON l.id=f.lexeme
                WHERE f.normalized=? AND l.pos='verb' AND l.target_safe=1""",(word,))}
            return tuple((head,relations[head]) for head in sorted(heads) if head in relations)
        noun_relations={language:NounRelations(db) for language,db in dictionaries.items()} if noun else {}
        @lru_cache(maxsize=100000)
        def resolve(source,word,target,counterpart):
            if noun:
                senses=noun_relations[source].source_relations(word)
                matches=[(head,links&senses) for head,links in noun_relations[target].heads(counterpart) if links&senses]
                if len(matches)!=1:return None,frozenset()
                return counterpart,matches[0][1]
            senses=source_relations(source,word)
            matches=[(head,links&senses) for head,links in target_relations(target,counterpart) if links&senses]
            # All native competing verb heads remain visible. Do not choose
            # whichever head has the most convenient reference frequency.
            if len(matches)!=1:return None,frozenset()
            return "@present:"+matches[0][0],matches[0][1]
        with closing(sqlite3.connect(args.observations.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)) as source,closing(sqlite3.connect(target)) as db:
            db.execute("PRAGMA temp_store=FILE");db.execute("PRAGMA cache_size=-16384")
            meta={k:json.loads(v) for k,v in db.execute("SELECT key,value FROM metadata")}
            assert meta["source_release_id"]==catalog["release_id"]
            db.executescript(f"""CREATE TABLE {table}(
                source TEXT NOT NULL,target TEXT NOT NULL,word TEXT NOT NULL,counterpart TEXT NOT NULL,cue TEXT NOT NULL,
                support INTEGER NOT NULL,total INTEGER NOT NULL,counterpart_support INTEGER NOT NULL,candidate_senses TEXT NOT NULL,
                PRIMARY KEY(source,target,word,counterpart,cue)) WITHOUT ROWID;
                CREATE TABLE {examples_table}(
                source TEXT,target TEXT,word TEXT,counterpart TEXT,cue TEXT,sentence INTEGER,translation INTEGER,
                PRIMARY KEY(source,target,word,counterpart,cue,sentence)) WITHOUT ROWID;""")
            atoms=dict(source.execute("SELECT id,value FROM atoms"))
            pairs={i:(a,b) for i,a,b in source.execute("SELECT * FROM pairs")}
            rows=source.execute("SELECT pair,word,cue,target,sentence,counterpart FROM observations ORDER BY pair,word,cue,target,sentence")
            for (pair,w,c),group in itertools.groupby(rows,lambda r:r[:3]):
                a,b=pairs[pair];word=atoms[w];cue=atoms[c];classified=[]
                for _,_,_,t,sid,tid in group:
                    head,senses=resolve(a,word,b,atoms[t])
                    classified.append((sid,tid,head,senses));counts["observations"]+=1
                    if head is None:counts["unresolved_observations"]+=1
                counts["contexts"]+=1
                for item in qualify(classified):
                    db.execute(f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?,?)",
                        (a,b,word,item["head"],cue,item["support"],item["total"],item["counterpart_support"],canonical(item["candidate_senses"])))
                    db.executemany(f"INSERT INTO {examples_table} VALUES (?,?,?,?,?,?,?)",
                        [(a,b,word,item["head"],cue,sid,tid) for sid,tid in item["evidence"]])
                    counts["alternatives"]+=1
                if counts["contexts"]%10000==0:
                    db.commit();print(canonical(dict(stage="contexts",counts=counts)),flush=True)
            recipe=dict(policy=policy,compiler_sha256=digest_file(Path(__file__)),
                observations_sha256=observed["sha256"],dictionary_catalog_sha256=digest_file(args.dictionary),
                base_runtime_sha256=base_pin["sha256"],minimum_source_sentences=3,minimum_relation_agreement=.98,
                minimum_counterpart_sentences=3,unique_source_votes=True,unknown_observations_retained=True,
                source_and_target_pos="noun" if noun else "verb",explicit_dictionary_relations_only=True,languages=sorted(dictionaries),
                runtime_grammar_checks_required=True,semantic_accuracy_claim=False)
            db.execute("INSERT INTO metadata VALUES (?,?)",(meta_prefix+"_policy",canonical(policy)))
            db.execute("INSERT INTO metadata VALUES (?,?)",(meta_prefix+"_recipe",canonical(recipe)))
            db.commit();assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
            db.execute("ATTACH DATABASE ? AS baseline",(args.base.resolve().as_uri()+"?mode=ro&immutable=1",))
            assert not db.execute("SELECT * FROM witnesses EXCEPT SELECT * FROM baseline.witnesses LIMIT 1").fetchone()
            assert not db.execute("SELECT * FROM baseline.witnesses EXCEPT SELECT * FROM witnesses LIMIT 1").fetchone()
            preserved_tables=["witnesses"]
            if noun:
                for name in ["semantic_alternatives","semantic_alternative_examples"]:
                    if db.execute("SELECT 1 FROM baseline.sqlite_master WHERE type='table' AND name=?",(name,)).fetchone():
                        assert not db.execute(f"SELECT * FROM {name} EXCEPT SELECT * FROM baseline.{name} LIMIT 1").fetchone()
                        assert not db.execute(f"SELECT * FROM baseline.{name} EXCEPT SELECT * FROM {name} LIMIT 1").fetchone()
                        preserved_tables.append(name)
            examples=db.execute(f"SELECT * FROM {table} WHERE source='en' AND word=? LIMIT 50",("home" if noun else "@present:drink",)).fetchall()
        receipt=dict(complete=True,sha256=digest_file(target),bytes=target.stat().st_size,
            counts=dict(counts),recipe=recipe,seconds=round(time.monotonic()-started,2),
            existing_witnesses_unchanged=True,preserved_tables=preserved_tables,independent_semantic_acceptance=False,production_promoted=False)
        (args.output/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
        (args.output/"examples.json").write_text(json.dumps(examples,ensure_ascii=False,indent=2)+"\n")
        (args.output/"ATTRIBUTION.txt").write_text(args.base.with_name("ATTRIBUTION.txt").read_text()+
            "\nExperimental aggregation of explicit dictionary relations; candidate labels are not asserted contextual meanings.\n")
        print(canonical(receipt),flush=True)
    finally:
        for db in dictionaries.values():db.close()
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ["observations","dictionary","base","output"]:p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--kind",choices=["present","noun"],default="present")
    p.add_argument("--languages",nargs="+",default=["en","es"],choices=["en","es","fr","de","pt"])
    build(p.parse_args())
