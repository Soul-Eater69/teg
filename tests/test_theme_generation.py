"""Theme generation (Contract C): per-VS fan-out, description ‖ stage selection."""

from __future__ import annotations

from teg.contracts.theme_io import (
    ApprovedValueStream,
    CondensedContext,
    ThemeGenerationRequest,
)
from teg.domain.condensed import GenerationSignals, SummaryFields
from teg.ingestion.catalogues.models import CatalogueStage, CatalogueValueStream
from teg.services.theme_service import ThemeService
from teg.theme.description import _GeneratedDescription
from teg.theme.stage_catalogue import StageCatalogue
from teg.theme.stage_selection import StageSelectionItem, StageSelectionResult


def _catalogue() -> StageCatalogue:
    vs = CatalogueValueStream(
        value_stream_id="VSR1",
        value_stream_name="Discover Business Insights",
        value_stream_description="Reporting and analytics about product use",
        value_proposition="",
        trigger="",
        category="",
        assumptions="",
        defined_terms="",
        active=True,
        created_date="",
        created_by="",
        modified_date="",
        modified_by="",
        stages=[
            CatalogueStage(
                stage_id="VSS1", stage_name="Explore Information", stage_description="explore",
                sequence=1, entrance_criteria="", exit_criteria="", value_items="", active=True,
                created_date="", modified_date="",
            ),
            CatalogueStage(
                stage_id="VSS2", stage_name="Publish Report", stage_description="publish",
                sequence=2, entrance_criteria="", exit_criteria="", value_items="", active=True,
                created_date="", modified_date="",
            ),
        ],
    )
    return StageCatalogue.from_catalogue([vs])


def _request() -> ThemeGenerationRequest:
    return ThemeGenerationRequest(
        ticket_id="IDMT-9",
        ticket_title="CP 2027 Guided Health Plans",
        condensed=CondensedContext(
            summary_fields=SummaryFields(
                generated_summary="Reporting and analytics about member product use",
                business_problem="No unified analytics",
                business_capability="Member analytics",
            ),
            generation_signals=GenerationSignals(plan_signals=["IL, TX, OK"], reporting_signals=["dashboards"]),
        ),
        approved_value_streams=[ApprovedValueStream(value_stream_id="VSR1", value_stream_name="Discover Business Insights")],
    )


class RoutingFakeLLM:
    """Returns the description text or the stage selection based on the requested schema."""

    description_text = (
        "Theme Description and Product Availability:\n"
        "The scope of this theme covers reporting and analytics.\n\n"
        "Product Availability:\nPlans: IL, TX, OK"
    )

    async def complete(self, *, system, user, schema):
        if schema is _GeneratedDescription:
            return _GeneratedDescription(text=self.description_text)
        return StageSelectionResult(
            stage_scope="specific_stages",
            selected_stages=[StageSelectionItem(stage_id="VSS1", reason="card centers on exploring information")],
        )


async def test_generate_one_package_description_and_stages() -> None:
    service = ThemeService(_catalogue(), RoutingFakeLLM(), model_name="gpt-x")
    response = await service.generate(_request())

    assert response.ticket_id == "IDMT-9"
    assert len(response.theme_packages) == 1
    pkg = response.theme_packages[0]
    assert pkg.value_stream_id == "VSR1"
    assert pkg.theme_title == "CP 2027 Guided Health Plans - Discover Business Insights"
    # the consolidated description is a single text block
    assert pkg.theme_description.startswith("Theme Description and Product Availability:")
    assert "Plans: IL, TX, OK" in pkg.theme_description
    # stage selection resolved to the governed stage (canonical name), no rank/evidence
    assert [s.stage_id for s in pkg.selected_stages] == ["VSS1"]
    assert pkg.selected_stages[0].stage_name == "Explore Information"
    assert pkg.selected_stages[0].reason.startswith("card centers")


async def test_invented_stage_id_is_dropped() -> None:
    class InventLLM(RoutingFakeLLM):
        async def complete(self, *, system, user, schema):
            if schema is _GeneratedDescription:
                return _GeneratedDescription(text="x")
            return StageSelectionResult(
                stage_scope="specific_stages",
                selected_stages=[StageSelectionItem(stage_id="NOT-A-STAGE", reason="r")],
            )

    service = ThemeService(_catalogue(), InventLLM())
    pkg = (await service.generate(_request())).theme_packages[0]
    assert pkg.selected_stages == []  # invented id not in the governed catalogue -> dropped
