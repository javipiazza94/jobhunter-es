"""Contrato API ↔ dashboard: todo campo que declaran los tipos TypeScript existe en el modelo de
Pydantic correspondiente, así que no puede leer un campo que la API no envía (o que se renombró)."""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import schemas  # noqa: E402
import setup_builder  # noqa: E402
from automation import application_documents, offer_evaluation, profile_proposal  # noqa: E402
from search_config import AISettings  # noqa: E402

FRONTEND_LIB = Path(__file__).parent.parent.parent / "frontend" / "lib"

# interfaz de TypeScript → modelo de Pydantic
PAIRS = {
    "Stats": schemas.StatsOut,
    "DashboardStats": schemas.DashboardStatsOut,
    "Company": schemas.CompanyOut,
    "JobOffer": schemas.OfferOut,
    "Application": schemas.ApplicationOut,
    "PendingApplication": schemas.PendingApplicationOut,
    "ContactOffer": schemas.ContactOfferOut,
    "Contact": schemas.ContactOut,
    "HistoryEntry": schemas.HistoryEntryOut,
    "InboxFile": schemas.InboxFileOut,
    "InboxReport": schemas.InboxReportOut,
    "InboxStatus": schemas.InboxStatusOut,
    "QuietApplication": schemas.QuietApplicationOut,
    "Track": schemas.TrackOut,
    "SetupStatus": schemas.SetupStatusOut,
    "MarketSource": schemas.MarketSourceOut,
    "TargetDraft": profile_proposal.TargetDraft,
    "ExperienceDraft": profile_proposal.ExperienceDraft,
    "LanguageDraft": profile_proposal.LanguageDraft,
    "EligibilityDraft": profile_proposal.EligibilityDraft,
    "ProfileDraft": profile_proposal.ProfileDraft,
    "SetupProposal": schemas.SetupProposalOut,
    "AISettings": AISettings,
    "SetupAnswers": setup_builder.SetupAnswers,
    "SetupApplyResult": schemas.SetupApplyOut,
    "AISettingsView": schemas.AISettingsOut,
    "AISettingsUpdate": schemas.AISettingsIn,
    "EmailSettingsView": schemas.EmailSettingsOut,
    "EmailSettingsUpdate": schemas.EmailSettingsIn,
    "CheckResult": schemas.CheckOut,
    "InterviewPack": schemas.InterviewPackOut,
    "SourceSetting": schemas.SourceSettingOut,
    "SourcesUpdate": schemas.SourcesIn,
    "AIKeyUpdate": schemas.AIKeyIn,
    "AIKeyResult": schemas.AIKeyOut,
    "JobStarted": schemas.JobStartedOut,
    "PrepareRequest": schemas.PrepareIn,
    "PreparedDocs": application_documents.PreparedDocs,
    "DocumentFile": schemas.DocumentFileOut,
    "EvaluationSummary": schemas.EvaluationSummaryOut,
    "OfferEvaluation": offer_evaluation.Evaluation,
    "EvaluationBatchItem": offer_evaluation.BatchItem,
    "EvaluationBatchResult": offer_evaluation.BatchResult,
    "EvaluateBatchRequest": schemas.EvaluateBatchIn,
    "CompanyResearch": schemas.CompanyResearchOut,
    "ScreeningAnswerSaved": schemas.ScreeningAnswerIn,
    "ScreeningQuestion": schemas.ScreeningQuestionIn,
    "ScreeningRequest": schemas.ScreeningRequestIn,
    "ScreeningAnswer": schemas.ScreeningAnswerOut,
    "ScreeningResult": schemas.ScreeningResultOut,
    "UpskillRequest": schemas.UpskillIn,
    "UpskillGap": schemas.UpskillGapOut,
    "UpskillReport": schemas.UpskillOut,
    "ExpandRequest": schemas.ExpandIn,
    "ExpandProposal": schemas.ExpandProposalOut,
    "ExpandError": schemas.ExpandErrorOut,
    "ExpandResult": schemas.ExpandOut,
    "ExpandAcceptRequest": schemas.ExpandAcceptIn,
    "ExpandAcceptResult": schemas.ExpandAcceptOut,
}


def _ts_interfaces() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for ts in ("types.ts", "api.ts"):
        src = (FRONTEND_LIB / ts).read_text(encoding="utf-8")
        for name, body in re.findall(r"interface (\w+) \{(.*?)\n\}", src, re.S):
            found[name] = set(re.findall(r"^\s+(\w+)\??:", body, re.M))
    return found


TS = _ts_interfaces()


@pytest.mark.parametrize("ts_name, model", PAIRS.items())
def test_los_campos_de_typescript_existen_en_el_modelo(ts_name, model):
    assert ts_name in TS, f"No encuentro la interfaz {ts_name} en frontend/lib"
    faltan = TS[ts_name] - set(model.model_fields)
    assert not faltan, f"{ts_name} (TS) usa campos que {model.__name__} no declara: {sorted(faltan)}"


def test_el_modelo_no_pierde_columnas_extra():
    # extra="allow": una columna nueva de la BD llega al frontend sin tocar los modelos.
    fila = schemas.OfferOut(id="1", title="Dev", columna_nueva="x")
    assert fila.model_dump()["columna_nueva"] == "x"


def test_cuerpos_incompletos_llegan_al_handler_con_valores_por_defecto():
    assert schemas.CoverLetterIn().cover_letter_edited == ""
    assert schemas.OutcomeIn().outcome == ""
