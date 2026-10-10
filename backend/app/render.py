


from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from .schemas import Resume
from .phase2l import preprocess_resume

TEMPLATE_DIR = Path(__file__).parent / "templates"
env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape(["html", "xml"])
)


def render_resume(resume: Resume | dict, measure: bool = True, renderer_contract_version: str = "legacy", sort_modes: dict | None = None, date_format: str = "long") -> str:
    data = resume.model_dump() if isinstance(resume, Resume) else resume
    return env.get_template("resume.html").render(
        resume=preprocess_resume(data, sort_modes, date_format), measure=measure,
        renderer_contract_version=renderer_contract_version,
    )

