# arXiv Submission Guide — MAREF TLA+ 5 Theorems

> **Paper**: `main.tex` + `references.bib`
> **Target**: arXiv (cs.MA primary, cs.SE cross-list)
> **D1 gate**: This submission unblocks G1 (`G1_arxiv_id`) in `STATE.yaml`

---

## 1. arXiv Submission Metadata

| Field | Value |
|-------|-------|
| **Title** | Formal Verification of Agent Governance: Five Theorems on the MAREF 10-State Gray Code State Machine |
| **Abstract** | See `main.tex` `\begin{abstract}` block (200 words) |
| **Authors** | MAREF Engineering (collective; or named authors if the human submitter prefers) |
| **Primary category** | `cs.MA` (Multi-Agent Systems) |
| **Cross-list category** | `cs.SE` (Software Engineering) |
| **Secondary cross-list** | `cs.LO` (Logic in Computer Science) — optional |
| **License** | arXiv non-exclusive license (compatible with Apache 2.0) |
| **Comments** | "12 pages, 5 theorems, TLA+ specifications included. Companion code: https://github.com/maref-org/maref" |
| **MSC classes** | 68Q85 (Automata theory, formal languages) — optional |
| **ACM classes** | D.2.4 (Software/Program Verification) — optional |
| **Report number** | MAREF-FV-2026-01 |
| **Journal reference** | (leave blank — this is a preprint) |
| **DOI** | (assigned by arXiv after submission) |
| **Subjects** | Multi-agent systems; formal verification; TLA+ |

---

## 2. Pre-Submission Checklist

Before submitting to arXiv, the human submitter must:

### 2.1 Build the PDF

```bash
cd $PROJECT_ROOT/docs/arxiv/maref-tla-plus-5-theorems/

# Option A: pdflatex (standard)
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex

# Option B: latexmk (automated)
latexmk -pdf main.tex

# Verify: main.pdf should be ~8-12 pages
ls -la main.pdf
```

### 2.2 Proofread

- [ ] Verify all 5 theorems render correctly with proper math notation
- [ ] Check TLA+ code listings render with syntax highlighting (the `listings` package + custom `TLA+` language)
- [ ] Verify bibliography renders (10 references expected)
- [ ] Check hyperlinks work (OWASP, Gartner, GitHub repo, etc.)
- [ ] Confirm abstract is under 250 words (arXiv limit)
- [ ] Confirm no LaTeX warnings about undefined references

### 2.3 Run TLC (optional but recommended for evidence)

```bash
cd $PROJECT_ROOT/src/formal/

# Run TLC on the configured .cfg files
java -cp tla2tools.jar tlc2.TLC MarefLiteModel.cfg
java -cp tla2tools.jar tlc2.TLC MAREF_ConstitutionalRedLines.cfg

# Save the output logs as supplementary evidence
# (the paper references TLC verification; having logs strengthens the claim)
```

### 2.4 Create arXiv Submission Package

arXiv requires a single .tar.gz or .zip archive containing:
- `main.tex`
- `references.bib`
- Any figures (none in this paper — all diagrams are tables/code)
- `main.pdf` (optional but speeds up arXiv processing)

```bash
cd $PROJECT_ROOT/docs/arxiv/maref-tla-plus-5-theorems/
tar -czf maref-tla-plus-5-theorems.tar.gz main.tex references.bib main.pdf
```

---

## 3. arXiv Submission Steps (Human Execution)

1. **Log in** to [arXiv](https://arxiv.org/) with the submitter's account
   - If no account: create one at https://arxiv.org/user/register
   - arXiv requires email verification + a brief endorsement/verification period for new submitters

2. **Start a new submission**
   - Go to https://arxiv.org/submit/
   - Click "Start a new submission"

3. **Fill metadata**
   - Title: "Formal Verification of Agent Governance: Five Theorems on the MAREF 10-State Gray Code State Machine"
   - Abstract: paste from `main.tex` (the content between `\begin{abstract}` and `\end{abstract}`)
   - Authors: "MAREF Engineering" or named authors
   - Categories: Primary = `cs.MA`, Cross-list = `cs.SE`
   - License: arXiv non-exclusive license to distribute
   - Comments: "12 pages, 5 theorems. Companion code: https://github.com/maref-org/maref"

4. **Upload the package**
   - Upload `maref-tla-plus-5-theorems.tar.gz`
   - arXiv will extract and attempt to build the PDF
   - Verify the built PDF looks correct

5. **Submit**
   - Click "Submit"
   - arXiv assigns an identifier immediately (e.g., `arXiv:2607.12345`)
   - The paper appears on arXiv within ~24 hours (may be longer for first-time submitters)

6. **Record the arXiv ID**
   - Copy the assigned arXiv ID (e.g., `2607.12345` or `cs.MA/260712345`)
   - Proceed to Section 4 below (G1 unlock)

---

## 4. G1 Gate Unlock Procedure

After obtaining the arXiv ID, update `STATE.yaml` to unblock the D1 G1 gate:

### 4.1 Update STATE.yaml

**File**: `$PROJECT_ROOT/STATE.yaml`

```yaml
# Before (current state):
d1_gate:
  G1_arxiv_id: false
  G2_branch_protection: true
  G3_ci_green: true
  G4_security_clean: true
  G5_no_runtime_artifacts: true
  gate_passed: false
  last_push_blocked_by: G1_arxiv_id
  allow_push_override: true
  override_reason: 'Temporary override: ...'

# After (update these fields):
d1_gate:
  G1_arxiv_id: true                    # ← changed to true
  G1_arxiv_id_value: 'arXiv:2607.XXXXX' # ← add the actual arXiv ID
  G2_branch_protection: true
  G3_ci_green: true
  G4_security_clean: true
  G5_no_runtime_artifacts: true
  gate_passed: true                     # ← now true (all G1-G5 pass)
  last_push_blocked_by: null            # ← no longer blocked
  allow_push_override: false            # ← override no longer needed
  override_reason: null                 # ← clear the override reason
```

### 4.2 Run D1 Pre-Flight Check

```bash
cd $PROJECT_ROOT/
python3 scripts/d1_preflight_check.py
```

This should now report all gates passing. If `G1_arxiv_id` still shows `false`,
the check script may need updating to read the `G1_arxiv_id_value` field.

### 4.3 Push to maref-org/maref (D1c)

Once all gates pass, the repository can be pushed without the override:

```bash
cd $PROJECT_ROOT/
# The .push_allow sentinel file is no longer needed:
rm -f .push_allow
git push origin main
```

If the pre-push hook still blocks (it may cache the override state), verify:
```bash
cat .git/hooks/pre-push  # Check the hook logic
git remote -v            # Confirm remote is maref-org/maref
```

---

## 5. Post-Submission Actions

- [ ] Add the arXiv link to the MAREF README.md under "Academic Publications"
- [ ] Update the MAREF website blog to cross-reference the arXiv preprint
- [ ] Post the arXiv link to Twitter/X, 知乎, and GitHub Discussions
- [ ] Update `STATE.yaml` (Section 4 above)
- [ ] Verify D1 pre-flight check passes
- [ ] Remove `allow_push_override` from STATE.yaml
- [ ] Close the G1 gate tracking issue in GitHub

---

## 6. Fallback Plan

If the arXiv submission is rejected or delayed:

1. **Endorsement required**: If the submitter is a new arXiv user, they may need an endorsement from an existing arXiv author in `cs.MA` or `cs.SE`. Request endorsement via the arXiv endorsement system.
2. **Format issues**: If arXiv rejects the LaTeX build, check for missing packages (`listings`, `xcolor` are standard but may not be in arXiv's TeX distribution). Fall back to a simpler `verbatim` environment if `listings` fails.
3. **Category dispute**: If `cs.MA` is rejected, try `cs.SE` as primary.
4. **Keep the override**: If submission is delayed beyond W8, keep `allow_push_override: true` and document the delay in `override_reason`.

---

## 7. Verification

To verify this guide is complete:

- [x] arXiv metadata specified (title, abstract, authors, categories, license)
- [x] Pre-submission checklist (build PDF, proofread, run TLC, create package)
- [x] Submission steps (login, fill metadata, upload, submit, record ID)
- [x] G1 unlock procedure (update STATE.yaml, run pre-flight, push)
- [x] Post-submission actions (update README, post links, close issue)
- [x] Fallback plan (endorsement, format issues, category dispute)

**Paper files**:
- [main.tex](main.tex) — LaTeX source (~4000 words, 5 theorems)
- [references.bib](references.bib) — bibliography (10 entries)
- [SUBMISSION_GUIDE.md](SUBMISSION_GUIDE.md) — this file
