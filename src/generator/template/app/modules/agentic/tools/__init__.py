"""Registre de tools appelables par le moteur agentic (Chap 15).

Un tool = callable async `(context, step_def) -> dict`. Les tools encapsulent les
appels d'API externes (Suno, etc.) et sont référencés **par nom** depuis
`agent_services.yaml` (`type: tool`, `tool: <nom>`). Ils vivent ici pour être
réutilisables par tout projet de la fabrique. Un projet ajoute un tool métier en
étendant ce registre depuis son overlay.
"""

from app.modules.agentic.tools.suno import suno_generate

TOOLS = {
    "suno_generate": suno_generate,
}


def get_tool(name: str):
    return TOOLS.get(name)
