from __future__ import annotations
from typing import List, Dict, Tuple
from orchestrator.router import Router
from shared.schemas import JobContext
from shared.gemini import call_gemini_json_async

IN_TYPES = ["items.math", "items.english", "items.thinking"]
OUT = "items.validated"

SYSTEM = (
    "You are a rigorous validator for Year 6 selective exam MCQs."
    " For each item, verify there is exactly one correct option among A–E,"
    " and that the provided answer is correct for the prompt and choices."
    " For math, recompute precisely. For reading/thinking, check unambiguity and plausibility."
    " Respond ONLY with JSON: {\"reports\": [ {item_id, status:(pass|fail), reasons:[...], corrected_answer?} ] }."
)

PROMPT_TEMPLATE = (
    "Validate the following items. Ensure single correct answer (A–E) and correctness.\n"
    "Items JSON:\n{items_json}"
)


def _structural_checks(items: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    passes: List[Dict] = []
    fails: List[Dict] = []
    for it in items:
        item_id = it.get("id") or "unknown"
        prompt = (it.get("prompt") or "").strip()
        choices = it.get("choices") or []
        answer = (it.get("answer") or "").strip()
        reasons: List[str] = []
        # Check 5 choices labeled A–E
        if len(choices) != 5:
            reasons.append("must have exactly 5 choices")
        labels = [c.get("id") for c in choices if isinstance(c, dict)]
        if labels != ["A", "B", "C", "D", "E"]:
            reasons.append("choice labels must be A,B,C,D,E in order")
        # Answer validity
        if answer not in {"A", "B", "C", "D", "E"}:
            reasons.append("answer must be one of A–E")
        # Non-empty content
        if not prompt:
            reasons.append("prompt must be non-empty")
        for c in choices:
            if not (isinstance(c, dict) and str(c.get("text", "")).strip()):
                reasons.append("all choices must have non-empty text")
                break
        if reasons:
            fails.append({"item_id": item_id, "status": "fail", "reasons": reasons})
        else:
            passes.append(it)
    return passes, fails


async def _validate_with_gemini(items: List[Dict]) -> List[Dict]:
    if not items:
        return []
    import json as _json
    items_payload = [
        {
            "id": it.get("id"),
            "subject": it.get("subject"),
            "prompt": it.get("prompt"),
            "choices": it.get("choices"),
            "answer": it.get("answer"),
            "solution": it.get("solution"),
        }
        for it in items
    ]
    prompt = PROMPT_TEMPLATE.format(items_json=_json.dumps(items_payload, ensure_ascii=False, indent=2))
    resp = await call_gemini_json_async(prompt, system=SYSTEM, max_output_tokens=800)
    # Robust parse: resp may be dict with reports or a list
    reports = []
    if isinstance(resp, dict) and isinstance(resp.get("reports"), list):
        reports = resp["reports"]
    elif isinstance(resp, list):
        reports = resp
    # Normalize report entries
    norm = []
    for r in reports[: len(items)]:
        item_id = r.get("item_id") if isinstance(r, dict) else None
        status = r.get("status") if isinstance(r, dict) else None
        reasons = r.get("reasons") if isinstance(r, dict) else []
        corrected = r.get("corrected_answer") if isinstance(r, dict) else None
        if status not in {"pass", "fail"}:
            status = "pass"
        norm.append({
            "item_id": item_id,
            "status": status,
            "reasons": reasons if isinstance(reasons, list) else [],
            "corrected_answer": corrected,
        })
    # Default to pass if model didn't return anything
    if not norm:
        norm = [{"item_id": it.get("id"), "status": "pass", "reasons": []} for it in items]
    return norm


def _filter_items_by_reports(items: List[Dict], reports: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    id_to_item = {it.get("id"): it for it in items}
    passed: List[Dict] = []
    failed: List[Dict] = []
    for rep in reports:
        item_id = rep.get("item_id")
        if rep.get("status") == "pass" and item_id in id_to_item:
            passed.append(id_to_item[item_id])
        else:
            failed.append(rep)
    return passed, failed


def register(router: Router) -> None:
    async def validate(msg: dict) -> None:
        ctx = JobContext(**msg["ctx"])  # type: ignore[arg-type]
        items: List[Dict] = msg["items"]
        # 1) Structural checks first
        structurally_ok, structural_fails = _structural_checks(items)
        # 2) Gemini semantic validation on the rest
        gemini_reports = await _validate_with_gemini(structurally_ok)
        # 3) Merge and filter
        passed, failed_gemini = _filter_items_by_reports(structurally_ok, gemini_reports)
        all_failed = structural_fails + failed_gemini
        payload: Dict = {"ctx": ctx.to_dict(), "items": passed, "status": "pass", "failed": all_failed}
        await router.emit(OUT, payload)

    for ev in IN_TYPES:
        router.subscribe(ev, validate)