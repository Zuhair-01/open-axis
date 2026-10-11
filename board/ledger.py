"""Work ledger (Car P10, 2026-10-11): one GitHub issue = one task card in Zuhair-01/zoher-ops, so Zoher and
every engine (Claude, Codex, Cursor, OpenCode) see the same plan, progress and next step, and any engine can
continue after another hits a limit WITHOUT redoing or overlapping work.

Card body = hidden lease block + checklist steps S1..Sn (each ticked step carries its evidence).
Checkpoint only at meaningful moments: plan approved, step done+verified, before a long job, limit warning/hit,
blocked, ending. Each checkpoint is one short call.

  python ledger.py find "<text>"                                   dedup before creating a card
  python ledger.py new "<title>" --steps "S1 text;S2 text" --tier B [--files "a,b"]
  python ledger.py claim <n> --engine claude --session <id> [--lease-min 30]
  python ledger.py check <n> S2 --evidence "<commit sha | test cmd | path>"
  python ledger.py checkpoint <n> --done "..." --next "exact next action" [--blockers "..."]
  python ledger.py handoff <n> --next "exact next action"         release for another engine
  python ledger.py resume <n>                                      what is left + last next action
  python ledger.py close <n>
"""
import argparse, json, re, subprocess, sys, time

REPO = "Zuhair-01/zoher-ops"
LEASE_RE = re.compile(r"<!-- ledger (\{.*?\}) -->")


def gh(*args, input_text=None):
    """Single choke point for GitHub calls (tests replace it)."""
    r = subprocess.run(["gh", *args], capture_output=True, text=True, input=input_text, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])} failed: {r.stderr.strip()[:300]}")
    return r.stdout


def load(n):
    d = json.loads(gh("issue", "view", str(n), "-R", REPO, "--json", "number,title,body,labels,state,comments"))
    m = LEASE_RE.search(d["body"] or "")
    d["lease"] = json.loads(m.group(1)) if m else {"claimed_by": None, "lease_until": 0}
    d["labels"] = [l["name"] for l in d["labels"]]
    return d


def save_body(n, body, lease):
    body = LEASE_RE.sub(f"<!-- ledger {json.dumps(lease)} -->", body) if LEASE_RE.search(body) \
        else f"<!-- ledger {json.dumps(lease)} -->\n" + body
    gh("issue", "edit", str(n), "-R", REPO, "--body-file", "-", input_text=body)


def set_status(n, labels, status):
    rm = [l for l in labels if l.startswith("status:") and l != f"status:{status}"]
    args = ["issue", "edit", str(n), "-R", REPO, "--add-label", f"status:{status}"]
    for l in rm:
        args += ["--remove-label", l]
    gh(*args)


def steps(body):
    return [(m.group(1) == "x", m.group(2), m.group(3)) for m in
            re.finditer(r"^- \[( |x)\] (S\d+)\b[ —:-]*(.*)$", body or "", re.M)]


def cmd_find(a):
    out = json.loads(gh("issue", "list", "-R", REPO, "--state", "open", "--search", a.text, "--json", "number,title,labels"))
    for i in out:
        print(f"#{i['number']} {i['title']}  [{', '.join(l['name'] for l in i['labels'])}]")
    if not out:
        print("no open card matches")


def cmd_new(a):
    lines = [f"- [ ] S{i} — {s.strip()}" for i, s in enumerate(a.steps.split(";"), 1) if s.strip()]
    body = (f"<!-- ledger {json.dumps({'claimed_by': None, 'lease_until': 0})} -->\n## Plan\n" + "\n".join(lines)
            + (f"\n\n## Files expected\n{a.files}" if a.files else "") + "\n")
    url = gh("issue", "create", "-R", REPO, "--title", a.title, "--body-file", "-", "--label", "status:todo",
             "--label", f"tier:{a.tier}", input_text=body).strip()
    print(url)


def cmd_claim(a):
    d = load(a.n)
    now, lease = time.time(), d["lease"]
    who = f"{a.engine}:{a.session}"
    free = (not lease.get("claimed_by") or lease.get("lease_until", 0) < now or "status:handoff" in d["labels"]
            or lease.get("claimed_by") == who)
    if not free:
        left = int((lease["lease_until"] - now) / 60)
        print(f"REFUSED: #{a.n} claimed by {lease['claimed_by']} for {left} more min. Pick another card or wait.")
        sys.exit(2)
    save_body(a.n, d["body"], {"claimed_by": who, "lease_until": now + a.lease_min * 60})
    set_status(a.n, d["labels"], "doing")
    if load(a.n)["lease"].get("claimed_by") != who:  # someone wrote after us: they win, we back off
        print(f"LOST RACE on #{a.n}; another engine claimed it first.")
        sys.exit(3)
    print(f"CLAIMED #{a.n} by {who} until {time.strftime('%H:%M', time.localtime(now + a.lease_min * 60))}")


def _renew(d, minutes=30):
    lease = dict(d["lease"])
    if lease.get("claimed_by"):
        lease["lease_until"] = time.time() + minutes * 60
    return lease


def cmd_check(a):
    d = load(a.n)
    pat = re.compile(rf"^- \[ \] ({re.escape(a.step)})\b(.*)$", re.M)
    if not pat.search(d["body"]):
        print(f"{a.step} not found or already ticked on #{a.n}")
        sys.exit(1)
    body = pat.sub(lambda m: f"- [x] {m.group(1)}{m.group(2)}  ✔ evidence: `{a.evidence}`", d["body"], count=1)
    save_body(a.n, body, _renew(d))
    print(f"#{a.n} {a.step} done (evidence: {a.evidence})")


def cmd_checkpoint(a):
    d = load(a.n)
    gh("issue", "comment", str(a.n), "-R", REPO, "--body-file", "-", input_text=
       f"**Checkpoint** ({d['lease'].get('claimed_by') or 'unclaimed'})\n- Done: {a.done}\n- Next: {a.next}\n"
       f"- Blockers: {a.blockers or 'none'}")
    save_body(a.n, d["body"], _renew(d))
    print(f"#{a.n} checkpointed")


def cmd_handoff(a):
    d = load(a.n)
    gh("issue", "comment", str(a.n), "-R", REPO, "--body-file", "-", input_text=
       f"**Handoff** from {d['lease'].get('claimed_by')}\n- Next: {a.next}\n- Resume: skip ticked steps, re-verify the "
       f"last 1-2 by their evidence, continue from Next.")
    save_body(a.n, d["body"], {"claimed_by": None, "lease_until": 0})
    set_status(a.n, d["labels"], "handoff")
    print(f"#{a.n} released for handoff")


def cmd_resume(a):
    d = load(a.n)
    st = steps(d["body"])
    done = [s for ok, s, _ in st if ok]
    todo = [(s, t) for ok, s, t in st if not ok]
    nxt = next((re.search(r"- Next: (.*)", c["body"]).group(1) for c in reversed(d["comments"])
                if re.search(r"- Next: ", c["body"])), None)
    print(f"#{a.n} {d['title']}  [{', '.join(d['labels'])}]  claim={d['lease'].get('claimed_by')}")
    print(f"done: {', '.join(done) or 'none'}  (re-verify the last {min(2, len(done))} by their evidence)")
    for s, t in todo:
        print(f"todo: {s} {t}")
    print(f"next action: {nxt or (todo[0][0] + ' ' + todo[0][1] if todo else 'all steps done -> close')}")


def cmd_close(a):
    d = load(a.n)
    save_body(a.n, d["body"], {"claimed_by": None, "lease_until": 0})
    set_status(a.n, d["labels"], "done")
    gh("issue", "close", str(a.n), "-R", REPO)
    print(f"#{a.n} closed")


def main(argv=None):
    p = argparse.ArgumentParser(prog="ledger")
    s = p.add_subparsers(dest="cmd", required=True)
    x = s.add_parser("find"); x.add_argument("text")
    x = s.add_parser("new"); x.add_argument("title"); x.add_argument("--steps", required=True)
    x.add_argument("--tier", default="C", choices=list("ABCD")); x.add_argument("--files", default="")
    x = s.add_parser("claim"); x.add_argument("n", type=int); x.add_argument("--engine", required=True)
    x.add_argument("--session", required=True); x.add_argument("--lease-min", type=int, default=30)
    x = s.add_parser("check"); x.add_argument("n", type=int); x.add_argument("step"); x.add_argument("--evidence", required=True)
    x = s.add_parser("checkpoint"); x.add_argument("n", type=int); x.add_argument("--done", required=True)
    x.add_argument("--next", required=True); x.add_argument("--blockers", default="")
    x = s.add_parser("handoff"); x.add_argument("n", type=int); x.add_argument("--next", required=True)
    for c in ("resume", "close"):
        x = s.add_parser(c); x.add_argument("n", type=int)
    a = p.parse_args(argv)
    globals()[f"cmd_{a.cmd}"](a)


if __name__ == "__main__":
    main()
