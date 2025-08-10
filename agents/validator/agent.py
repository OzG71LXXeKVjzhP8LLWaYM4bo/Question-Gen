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
    " If an image description is provided, ensure the question uses only information derivable from that description."
    " Respond ONLY with JSON: {\"reports\": [ {item_id, status:(pass|fail), reasons:[...], corrected_answer?} ] }."
)

PROMPT_TEMPLATE = (
    "Validate the following items. Ensure single correct answer (A–E) and correctness.\n"
    "If image_description is provided, the problem must rely on it and be solvable from it alone.\n"
    "Items JSON:\n{items_json}"
)


def _structural_checks(items: List[Dict], ctx: JobContext) -> Tuple[List[Dict], List[Dict]]:
    passes: List[Dict] = []
    fails: List[Dict] = []
    image = ctx.constraints.get("image") if isinstance(ctx.constraints, dict) else None
    for it in items:
        item_id = it.get("id") or "unknown"
        prompt = (it.get("prompt") or "").strip()
        choices = it.get("choices") or []
        answer = (it.get("answer") or "").strip()
        reasons: List[str] = []
        if len(choices) != 5:
            reasons.append("must have exactly 5 choices")
        labels = [c.get("id") for c in choices if isinstance(c, dict)]
        if labels != ["A", "B", "C", "D", "E"]:
            reasons.append("choice labels must be A,B,C,D,E in order")
        if answer not in {"A", "B", "C", "D", "E"}:
            reasons.append("answer must be one of A–E")
        if not prompt:
            reasons.append("prompt must be non-empty")
        for c in choices:
            if not (isinstance(c, dict) and str(c.get("text", "")).strip()):
                reasons.append("all choices must have non-empty text")
                break
        # Image reference required when image is provided
        if isinstance(image, dict) and image.get("description"):
            if "image" not in prompt.lower() and "graph" not in prompt.lower() and "diagram" not in prompt.lower():
                reasons.append("prompt must reference the image when image_description is provided")
            it["uses_image"] = True
            it["image_description"] = str(image.get("description"))[:500]
            it["image_type"] = str(image.get("type") or "other")
        if reasons:
            fails.append({"item_id": item_id, "status": "fail", "reasons": reasons, "subject": it.get("subject")})
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
            "image_description": it.get("image_description"),
        }
        for it in items
    ]
    prompt = PROMPT_TEMPLATE.format(items_json=_json.dumps(items_payload, ensure_ascii=False, indent=2))
    resp = await call_gemini_json_async(prompt, system=SYSTEM, max_output_tokens=800)
    reports = []
    if isinstance(resp, dict) and isinstance(resp.get("reports"), list):
        reports = resp["reports"]
    elif isinstance(resp, list):
        reports = resp
    norm = []
    for r in reports[: len(items)]:
        item_id = r.get("item_id") if isinstance(r, dict) else None
        status = r.get("status") if isinstance(r, dict) else None
        reasons = r.get("reasons") if isinstance(r, dict) else []
        corrected = r.get("corrected_answer") if isinstance(r, dict) else None
        subject = next((it.get("subject") for it in items if it.get("id") == item_id), None)
        if status not in {"pass", "fail"}:
            status = "pass"
        norm.append({
            "item_id": item_id,
            "status": status,
            "reasons": reasons if isinstance(reasons, list) else [],
            "corrected_answer": corrected,
            "subject": subject,
        })
    if not norm:
        norm = [{"item_id": it.get("id"), "status": "pass", "reasons": [], "subject": it.get("subject")} for it in items]
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
        structurally_ok, structural_fails = _structural_checks(items, ctx)
        gemini_reports = await _validate_with_gemini(structurally_ok)
        passed, failed_gemini = _filter_items_by_reports(structurally_ok, gemini_reports)
        all_failed = structural_fails + failed_gemini
        payload: Dict = {"ctx": ctx.to_dict(), "items": passed, "status": "pass", "failed": all_failed}
        await router.emit(OUT, payload)

    for ev in IN_TYPES:
        router.subscribe(ev, validate)