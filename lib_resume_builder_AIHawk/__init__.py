import base64
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
import yaml
from pydantic import BaseModel, EmailStr, HttpUrl, Field
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors


class PersonalInformation(BaseModel):
    name: Optional[str] = None
    surname: Optional[str] = None
    date_of_birth: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    zip_code: Optional[str] = None
    phone_prefix: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    github: Optional[str] = None
    linkedin: Optional[str] = None


class EducationDetails(BaseModel):
    education_level: Optional[str] = None
    institution: Optional[str] = None
    field_of_study: Optional[str] = None
    final_evaluation_grade: Optional[str] = None
    start_date: Optional[str] = None
    year_of_completion: Optional[Union[int, str]] = None
    exam: Optional[Any] = None


class ExperienceDetails(BaseModel):
    position: Optional[str] = None
    company: Optional[str] = None
    employment_period: Optional[str] = None
    location: Optional[str] = None
    industry: Optional[str] = None
    key_responsibilities: Optional[Any] = None
    skills_acquired: Optional[List[str]] = None


class Project(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    link: Optional[str] = None


class Achievement(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class Certifications(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class Language(BaseModel):
    language: Optional[str] = None
    proficiency: Optional[str] = None


class Resume(BaseModel):
    personal_information: Optional[PersonalInformation] = None
    education_details: Optional[List[EducationDetails]] = None
    experience_details: Optional[List[ExperienceDetails]] = None
    projects: Optional[List[Project]] = None
    achievements: Optional[List[Achievement]] = None
    certifications: Optional[List[Certifications]] = None
    languages: Optional[List[Language]] = None
    interests: Optional[List[str]] = None

    def __init__(self, yaml_str: str):
        try:
            data = yaml.safe_load(yaml_str)
            if not isinstance(data, dict):
                data = {}
            super().__init__(**data)
        except Exception as e:
            super().__init__()


class StyleManager:
    def __init__(self):
        pass

    def get_styles(self):
        return {"default": ("default.css", "")}

    def format_choices(self, available_styles):
        return list(available_styles.keys())

    def set_selected_style(self, style_name):
        pass

    def get_style_path(self):
        return None


class ResumeGenerator:
    def __init__(self):
        self.resume_object = None

    def set_resume_object(self, resume_object):
        self.resume_object = resume_object

    def generate_pdf(self, resume_object, output_pdf_path: str):
        import os
        os.makedirs(os.path.dirname(os.path.abspath(output_pdf_path)), exist_ok=True)
        doc = SimpleDocTemplate(
            output_pdf_path,
            pagesize=letter,
            rightMargin=40,
            leftMargin=40,
            topMargin=40,
            bottomMargin=40,
        )
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Heading1'],
            fontSize=18,
            leading=22,
            textColor=colors.HexColor('#1a365d'),
            alignment=1,
            spaceAfter=6,
        )
        sub_style = ParagraphStyle(
            'SubStyle',
            parent=styles['Normal'],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor('#4a5568'),
            alignment=1,
            spaceAfter=15,
        )
        heading_style = ParagraphStyle(
            'HeadingStyle',
            parent=styles['Heading2'],
            fontSize=13,
            leading=16,
            textColor=colors.HexColor('#2b6cb0'),
            spaceBefore=10,
            spaceAfter=6,
        )
        body_style = ParagraphStyle(
            'BodyStyle',
            parent=styles['Normal'],
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor('#2d3748'),
            spaceAfter=4,
        )

        elements = []
        p_info = getattr(resume_object, 'personal_information', None)
        name = f"{getattr(p_info, 'name', '')} {getattr(p_info, 'surname', '')}".strip() or "Candidate"
        city = getattr(p_info, 'city', '') or "Edmonton"
        country = getattr(p_info, 'country', '') or "Canada"
        email = getattr(p_info, 'email', '') or ""
        phone = getattr(p_info, 'phone', '') or ""

        elements.append(Paragraph(f"<b>{name.upper()}</b>", title_style))
        contact_line = f"{city}, {country} | {phone} | {email}"
        elements.append(Paragraph(contact_line, sub_style))

        elements.append(Paragraph("<b>PROFESSIONAL EXPERIENCE</b>", heading_style))
        exp_list = getattr(resume_object, 'experience_details', []) or []
        for exp in exp_list:
            pos = getattr(exp, 'position', '')
            comp = getattr(exp, 'company', '')
            period = getattr(exp, 'employment_period', '')
            elements.append(Paragraph(f"<b>{pos}</b> — <i>{comp}</i> ({period})", body_style))
            resps = getattr(exp, 'key_responsibilities', []) or []
            for r in resps:
                desc = r.get('responsibility', '') if isinstance(r, dict) else str(r)
                if desc:
                    elements.append(Paragraph(f"• {desc}", body_style))
            elements.append(Spacer(1, 4))

        elements.append(Paragraph("<b>EDUCATION</b>", heading_style))
        edu_list = getattr(resume_object, 'education_details', []) or []
        for edu in edu_list:
            level = getattr(edu, 'education_level', '')
            field = getattr(edu, 'field_of_study', '')
            inst = getattr(edu, 'institution', '')
            year = getattr(edu, 'year_of_completion', '')
            elements.append(Paragraph(f"<b>{level} in {field}</b> — {inst} ({year})", body_style))

        doc.build(elements)
        with open(output_pdf_path, "rb") as f:
            return f.read()


class FacadeManager:
    def __init__(self, api_key, style_manager, resume_generator, resume_object, output_path):
        self.api_key = api_key
        self.style_manager = style_manager
        self.resume_generator = resume_generator
        self.resume_object = resume_object
        self.output_path = Path(output_path)
        self.output_path.mkdir(parents=True, exist_ok=True)
        self._cached_base64 = None

    def choose_style(self):
        pass

    def get_resume_country(self):
        try:
            if hasattr(self.resume_object, 'personal_information') and self.resume_object.personal_information:
                c = getattr(self.resume_object.personal_information, 'country', None)
                if c:
                    return str(c)
        except Exception:
            pass
        return 'Canada'

    def pdf_base64(self, job_description_text=None):
        if self._cached_base64:
            return self._cached_base64
        pdf_path = self.output_path / "generated_resume.pdf"
        pdf_bytes = self.resume_generator.generate_pdf(self.resume_object, str(pdf_path))
        self._cached_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
        return self._cached_base64


__all__ = ["Resume", "FacadeManager", "ResumeGenerator", "StyleManager"]
