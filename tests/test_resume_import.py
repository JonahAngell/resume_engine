import csv
import io
import zipfile
from pathlib import Path

from app.resume_import import (
    PROFILE_ONLY_NOTICE,
    TEXTLESS_PDF,
    TextLine,
    parse_text_resume,
    parse_upload,
)

ROOT = Path(__file__).resolve().parents[1]

RESUME_LINES = [
    "Jonah Angell",
    "jonah@example.com | 555-010-1234",
    "https://www.linkedin.com/in/jonahangell",
    "Summary",
    "Data scientist who builds reliable data platforms.",
    "Experience",
    "Acme Corp",
    "Data Scientist",
    "New York, NY",
    "Jan 2020 - Present",
    "- Built forecasting models",
    "- Cut pipeline runtime by 40%",
    "Northwind",
    "Analyst",
    "2018 - 2019",
    "- Reported weekly metrics",
    "Education",
    "State University",
    "B.S. in Statistics",
    "2018",
    "Skills",
    "Languages: Python, SQL",
    "Tools: Docker, Git",
    "Projects",
    "Forecast Bench",
    "A public benchmark",
    "2021",
    "- Published evaluation scripts",
    "Leadership",
    "City Library",
    "Volunteer Tutor",
    "2019 - 2020",
    "- Taught SQL workshops",
    "Interests",
    "Hiking, Chess",
]


def text_pdf(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 11 Tf", "72 760 Td"]
    for index, line in enumerate(lines):
        if index:
            commands.append("0 -14 Td")
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands.append(f"({escaped}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(output)
    output += f"xref\n0 {len(objects) + 1}\n".encode()
    output += b"0000000000 65535 f \n"
    for offset in offsets:
        output += f"{offset:010d} 00000 n \n".encode()
    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(output)


def text_docx(lines: list[str], present: str = "Jan 2020 - Present") -> bytes:
    from docx import Document

    document = Document()
    headings = {
        "Summary",
        "Experience",
        "Education",
        "Skills",
        "Projects",
        "Leadership",
        "Interests",
    }
    for line in lines:
        written = present if line == "Jan 2020 - Present" else line
        paragraph = document.add_paragraph(written)
        if written in headings:
            for run in paragraph.runs:
                run.bold = True
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def assert_resume(draft):
    assert draft.profile.name == "Jonah Angell"
    assert draft.profile.email == "jonah@example.com"
    assert "555-010-1234" in draft.profile.phone
    assert draft.profile.linkedin_url == "https://www.linkedin.com/in/jonahangell"
    assert "reliable data platforms" in draft.summary.body
    jobs = [entry for entry in draft.entries if entry.section == "employment"]
    assert jobs[0].organization == "Acme Corp"
    assert jobs[0].title == "Data Scientist"
    assert jobs[0].location == "New York, NY"
    assert jobs[0].is_current is True
    assert jobs[0].start_year == 2020
    assert jobs[0].start_month == 1
    assert jobs[0].end_year is None
    assert jobs[0].bullets == ["Built forecasting models", "Cut pipeline runtime by 40%"]
    assert jobs[1].organization == "Northwind"
    assert jobs[1].title == "Analyst"
    assert jobs[1].start_year == 2018
    assert jobs[1].end_year == 2019
    assert jobs[1].is_current is False
    education = [entry for entry in draft.entries if entry.section == "education"]
    assert education[0].institution == "State University"
    assert education[0].degree_type.lower().startswith("b")
    assert education[0].degree_major == "Statistics"
    assert education[0].graduation_year == 2018
    skills = {entry.name: entry.tools for entry in draft.entries if entry.section == "skills"}
    assert skills["Languages"] == ["Python", "SQL"]
    assert skills["Tools"] == ["Docker", "Git"]
    project = next(entry for entry in draft.entries if entry.section == "project")
    assert project.name == "Forecast Bench"
    assert project.subtitle == "A public benchmark"
    assert project.start_year == 2021
    assert project.bullets == ["Published evaluation scripts"]
    leadership = next(entry for entry in draft.entries if entry.section == "leadership")
    assert leadership.organization == "City Library"
    assert leadership.title == "Volunteer Tutor"
    interests = [entry.body for entry in draft.entries if entry.section == "interests"]
    assert interests == ["Hiking", "Chess"]


def test_pdf_resume_sections_dates_and_skills():
    draft = parse_upload("resume.pdf", text_pdf(RESUME_LINES))
    assert_resume(draft)


def test_docx_resume_treats_present_as_current():
    draft = parse_upload("resume.docx", text_docx(RESUME_LINES, "Jan 2020 – Present"))
    assert_resume(draft)


def test_image_only_pdf_asks_for_text():
    try:
        parse_upload("scan.pdf", text_pdf([]))
    except ValueError as exc:
        assert str(exc) == TEXTLESS_PDF
    else:
        raise AssertionError("empty PDF should fail")


def test_text_lines_keep_low_confidence_when_title_is_missing():
    draft = parse_text_resume(
        [
            TextLine("Experience"),
            TextLine("Acme Corp"),
            TextLine("Jan 2020 - Present"),
            TextLine("- Shipped the pipeline"),
        ]
    )
    job = draft.entries[0]
    assert job.organization == "Acme Corp"
    assert job.title == ""
    assert "title" in job.low_confidence


def _csv(name: str, rows: list[dict]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode()


def test_linkedin_zip_maps_columns_and_present_roles():
    payload = {
        "Profile.csv": _csv(
            "Profile.csv",
            [
                {
                    "First Name": "Jonah",
                    "Last Name": "Angell",
                    "Headline": "Data scientist",
                    "Summary": "Builds data platforms.",
                }
            ],
        ),
        "Positions.csv": _csv(
            "Positions.csv",
            [
                {
                    "Company Name": "Acme Corp",
                    "Title": "Data Scientist",
                    "Description": "Built forecasting models",
                    "Location": "New York, NY",
                    "Started On": "Jan 2020",
                    "Finished On": "",
                }
            ],
        ),
        "Education.csv": _csv(
            "Education.csv",
            [
                {
                    "School Name": "State University",
                    "Degree Name": "B.S. in Statistics",
                    "Start Date": "2014",
                    "End Date": "2018",
                    "Notes": "",
                }
            ],
        ),
        "Skills.csv": _csv("Skills.csv", [{"Name": "Python"}, {"Name": "SQL"}]),
    }
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        for name, data in payload.items():
            bundle.writestr(name, data)
    draft = parse_upload("Basic_LinkedInDataExport.zip", archive.getvalue())
    assert draft.notices == []
    assert draft.profile.name == "Jonah Angell"
    assert draft.summary.body == "Builds data platforms."
    job = next(entry for entry in draft.entries if entry.section == "employment")
    assert job.organization == "Acme Corp"
    assert job.is_current is True
    assert job.start_month == 1
    assert job.bullets == ["Built forecasting models"]
    education = next(entry for entry in draft.entries if entry.section == "education")
    assert education.institution == "State University"
    assert education.graduation_year == 2018
    skills = next(entry for entry in draft.entries if entry.section == "skills")
    assert skills.tools == ["Python", "SQL"]


def test_profile_csv_alone_warns_that_jobs_are_missing():
    draft = parse_upload(
        "Profile.csv",
        _csv(
            "Profile.csv",
            [{"First Name": "Jonah", "Last Name": "Angell", "Headline": "Data scientist", "Summary": "Hello"}],
        ),
    )
    assert draft.profile.name == "Jonah Angell"
    assert draft.entries == []
    assert draft.notices == [PROFILE_ONLY_NOTICE]


def test_import_ui_enables_home_button_and_explains_linkedin_downloads():
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    dialog = (ROOT / "frontend/src/ImportResumeDialog.tsx").read_text(encoding="utf-8")
    main = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    assert "Import Existing Resume" in app
    assert "Import from an existing resume is coming soon." not in app
    assert 'setScreen("import")' in app
    for text in (
        "Save your profile as a PDF",
        "Save to PDF",
        "Settings & Privacy",
        "Data privacy",
        "Get a copy of your data",
        "Want something in particular",
        "Positions",
        "Education",
        "Skills",
        "Add to library",
        "Original text",
        'aria-pressed',
        'aria-expanded',
        'aria-label="Section"',
    ):
        assert text in dialog
    assert "<select" not in dialog
    assert "/api/library/import/preview" in main
    assert "/api/library/import/commit" in main


def test_zip_bomb_is_rejected_before_decompression():
    import pytest

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Positions.csv", b"a," * (6 * 1024 * 1024))
    assert len(buffer.getvalue()) < 100_000
    with pytest.raises(ValueError, match="more data"):
        parse_upload("export.zip", buffer.getvalue())


def test_zip_with_too_many_entries_is_rejected():
    import pytest

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for index in range(60):
            archive.writestr(f"file{index}.txt", b"x")
    with pytest.raises(ValueError, match="more data"):
        parse_upload("export.zip", buffer.getvalue())
