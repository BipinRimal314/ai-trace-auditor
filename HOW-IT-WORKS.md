# How AI Trace Auditor Works

Written so I can explain this tool to anyone, including a skeptic who assumes anything built with AI assistance is smoke. It is not smoke. But the reason it is not smoke is the opposite of what most people expect, so read this before you defend it.

## The one idea

There is a new law, the EU AI Act. It says something simple: if you run an AI system, keep records. Write down what the AI was asked, what it answered, which model ran, and when.

AI Trace Auditor reads those records and tells you which of the required pieces are actually present and which are missing. Every check is tied to a specific line of a specific law.

That is the whole thing. If you understand that sentence, you understand the product. Everything below is just proof that the sentence is true.

## What actually happens when you run it

I ran it on one real session of my own Claude Code usage: 410 events, 860 KB of logs. Not a demo file. Real data my own tooling produced.

It returned a report: 91.2% overall, broken into Legal Compliance 100%, Structural Evidence 91%, Quality 60%. The gaps it flagged were things like "temperature parameter not logged" and "latency in milliseconds not logged." Those are real absences, and they are correctly sorted as quality niceties, not legal failures. That is why Legal scored 100% and Quality scored 60%.

## The part that is deliberately dumb

Here is the actual checking logic, for a requirement that asks whether a field is present:

```python
if check_type == "non_null":
    return value is not None
```

That is it. For each requirement, the tool asks one question of each event: is this field there, or not. It counts how many events have it, and turns that into a percentage.

Worked example, end to end:

1. The law: EU AI Act Article 12(1), "High-risk AI systems shall technically allow for the automatic recording of events."
2. The check: does each event carry a timestamp.
3. My real data: 331 of 410 events carried one.
4. The score: that number rolls up into the structural tier.

No neural network decides anything at runtime. No language model reads your logs and forms an opinion. A field exists or it does not; the tool counts, and it divides. Same input, same answer, every single time.

This is the point that disarms the "an AI just made this up" worry. The engine is so simple a skeptic can read it in five minutes and confirm it cannot hallucinate. Determinism is the feature, not a limitation.

## The part that is actually hard

The intelligence was never supposed to live in the code. The hard, defensible work is the mapping: reading the actual legal text and deciding which checkable field is a fair stand-in for each clause, then being honest about how fair that stand-in really is.

Look at how the tool stores that Article 12(1) requirement. It does not claim the law demands a timestamp. It marks the timestamp as a "defensible proxy" and records, in writing, that "absence is not a statutory failure if the system logs events by another mechanism." Every requirement carries this: whether the law prescribes the check exactly, requires a capability, or the check is just a reasonable proxy.

Most compliance tooling would never admit the difference. This one is built around admitting it.

## The failure that made it trustworthy

If someone pushes and asks whether an AI just invented these compliance rules, the honest answer is the strongest thing I can say.

Version 0.14 shipped with roughly 60% of its EU AI Act requirements fabricated. A language model had projected software-engineering assumptions onto legal text, and the result looked authoritative and was wrong. A maintainer of a real open-source AI project caught it.

So it was rebuilt around one rule: no requirement ships unless it quotes the exact clause ("Article 12(2)(a)") and has been checked, page by page, against the primary legal text. The docs call the underlying trap the abstraction-fabrication curve: the more abstract the jump from legal words to a code check, the higher the chance the model invented the connection. Concrete text patterns fabricate at 0%. Abstract legal-to-field mappings fabricated at 60%. The rule now is: write the legal quote first, then ask whether the check actually follows from those exact words.

A naive build ships the confident, wrong version and never learns. This one hit that failure, got caught by an expert, and turned the fix into its core design principle. That arc, from confidently wrong to verified with citations, is more rigor than most human-built compliance software carries.

## What it does not do (the honest limits)

Carry these unprompted and no expert can catch you overclaiming:

- The EU AI Act, NIST AI RMF, and GDPR requirements are verified against primary sources. ISO 42001 and SOC 2 are not, because those are paid standards the tool could not check against. It says so.
- It audits technical record-keeping. It cannot tell you whether your system is legally high-risk; that depends on your use case, not your logs.
- Zero real users so far. It works, it is on PyPI, it is live on the web. The open problem is distribution, not whether it functions.

## How to explain it in one breath

- What it is: a spell-checker for AI compliance. It reads your AI system's logs and tells you which record-keeping rules from the EU AI Act you pass or fail.
- How it does it: it checks whether specific fields (timestamps, inputs, outputs, model IDs) are present, and ties each check to an exact clause of the law. Deterministic, so it cannot make things up.
- What it is for: the compliance gap-analysis a law firm charges five or six figures for, run in seconds, so a team knows where it stands before a regulator does.
- When challenged on being AI-built: lead with the v0.14 failure. It is the credibility, not the weakness.
