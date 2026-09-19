from __future__ import annotations

import concurrent.futures
import json
import re
from typing import Any

from core import gemini


_DEFAULT_ROLES = [
    "researcher",
    "planner",
    "implementer",
    "reviewer",
    "verifier",
    "security",
    "fact_checker",
    "automation",
    "language",
    "performance",
]
_ROLE_BRIEFS = {
    "researcher": "Gather relevant facts, constraints, risks, and missing information.",
    "planner": "Turn the request into a concrete ordered plan with measurable outcomes.",
    "implementer": "Suggest the exact implementation or action steps, preserving existing behavior.",
    "reviewer": "Look for bugs, security risks, bad assumptions, and edge cases.",
    "verifier": "Define the cheapest checks that prove the result works and identify likely failure signals.",
    "security": "Check permissions, secrets, privacy, destructive actions, and safe confirmation boundaries.",
    "fact_checker": "Separate verified facts from guesses and identify information that needs live validation.",
    "automation": "Find reliable ways to execute the task using the available tools and operating system.",
    "language": "Improve Uzbek understanding and response clarity; preserve names, paths, and exact parameters.",
    "performance": "Reduce latency, unnecessary model calls, resource usage, and fragile dependencies.",
}
_ROLE_KEYWORDS = {
    "security": ("security", "password", "parol", "token", "api key", "maxfiy"),
    "fact_checker": ("latest", "today", "bugun", "news", "yangilik", "price", "narx"),
    "automation": ("open", "launch", "och", "yubor", "send", "install", "o'rnat"),
    "language": ("translate", "tarjima", "uzbek", "o'zbek", "til", "voice", "ovoz"),
    "performance": ("fast", "tez", "optimize", "optim", "slow", "sekin"),
    "reviewer": ("review", "tekshir", "xato", "bug", "debug", "fix", "tuzat"),
}


def _select_roles(task: str, budget: str) -> list[str]:
    """Choose a small useful team unless the caller explicitly requests depth."""
    normalized = task.casefold()
    if budget == "economy":
        limit = 2
    elif budget == "deep":
        limit = 8
    else:
        limit = 4

    selected = [role for role, words in _ROLE_KEYWORDS.items()
                if any(word in normalized for word in words)]
    baseline = ["planner", "implementer", "reviewer", "verifier"]
    for role in baseline:
        if role not in selected:
            selected.append(role)
        if len(selected) >= limit:
            break
    return selected[:limit]


def _clean(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json|text)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _ask(role: str, task: str, language: str) -> dict[str, str]:
    brief = _ROLE_BRIEFS.get(role, "Analyze the request from an independent expert perspective.")
    prompt = f"""You are the {role} agent in a controlled multi-agent assistant.
Task: {task}
Role: {brief}
Output language: {language}

Return concise, actionable findings. Do not claim that an action was performed.
Do not invent access, files, results, or permissions. Separate facts, assumptions,
risks, and recommendations when useful."""
    response = gemini.call(prompt, tier=gemini.SMART, timeout_ms=45_000)
    if response is None:
        raise RuntimeError("agent model returned no response")
    return {"role": role, "result": _clean(getattr(response, "text", ""))}


def _synthesize(task: str, reports: list[dict[str, str]], language: str) -> str:
    evidence = json.dumps(reports, ensure_ascii=False)
    prompt = f"""You are the lead agent. Synthesize these specialist reports for the task below.
Task: {task}
Reports:
{evidence}

Write a concise final answer in {language}. Resolve contradictions, distinguish verified
facts from suggestions, and give an ordered next step. Never claim that a tool or action
was executed unless a report explicitly verifies it."""
    response = gemini.call(prompt, tier=gemini.SMART, timeout_ms=60_000)
    if response is None:
        return "Agentlar natija qaytara olmadi."
    return _clean(getattr(response, "text", ""))


def multi_agent(parameters: dict, player=None, speak=None, **_: Any) -> str:
    params = parameters or {}
    task = str(params.get("task") or params.get("description") or "").strip()
    if not task:
        return "Ko‘p agentli vazifa uchun topshiriq kerak."

    language = str(params.get("language") or "Uzbek").strip()
    budget = str(params.get("budget") or "standard").strip().lower()
    if budget not in {"economy", "standard", "deep"}:
        budget = "standard"
    requested = params.get("roles") or _select_roles(task, budget)
    if isinstance(requested, str):
        requested = [item.strip().lower() for item in requested.split(",")]
    roles = [str(role).strip().lower() for role in requested if str(role).strip()]
    roles = list(dict.fromkeys(roles))[:8 if budget == "deep" else 4]
    if not roles:
        roles = _select_roles(task, budget)

    if player:
        player.write_log(f"[Agents] Started {len(roles)} specialist agents.")

    reports: list[dict[str, str]] = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(roles), thread_name_prefix="jarvis-agent"
    ) as executor:
        futures = {executor.submit(_ask, role, task, language): role for role in roles}
        for future in concurrent.futures.as_completed(futures):
            role = futures[future]
            try:
                reports.append(future.result())
            except Exception as error:
                reports.append({"role": role, "result": f"Agent failed: {error}"})

    reports.sort(key=lambda item: roles.index(item["role"]))
    successful = sum(not item["result"].startswith("Agent failed:") for item in reports)
    success_rate = round(successful / len(roles) * 100) if roles else 0
    if player:
        player.write_log(
            f"[Agents] Reports: {successful}/{len(roles)} successful; "
            f"success={success_rate}%; budget={budget}; "
            f"model calls={len(roles) + 1}."
        )
    result = _synthesize(task, reports, language)
    if player:
        player.write_log("[Agents] Specialist reports synthesized.")
    if speak:
        speak(result)
    return result


TOOL = {
    "name": "multi_agent",
    "description": (
        "Delegates a complex request to a cost-aware team of specialist agents in parallel, "
        "then synthesizes a verified plan. Use for research, planning, coding review, "
        "or multi-step analysis; it does not execute dangerous actions by itself."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "task": {"type": "STRING", "description": "The complex task to analyze."},
            "language": {"type": "STRING", "description": "Response language, for example Uzbek."},
            "budget": {
                "type": "STRING",
                "enum": ["economy", "standard", "deep"],
                "description": "economy uses 2 agents, standard uses up to 4, deep uses up to 8.",
            },
            "roles": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "Optional roles. If omitted, roles are selected from the task automatically.",
            },
        },
        "required": ["task"],
    },
    "handler": multi_agent,
}
