"""Theme generation (Contract C): per-VS fan-out, description ‖ stage selection."""

from __future__ import annotations

from teg.contracts.theme_io import (
    ApprovedValueStream,
    CondensedContext,
    ThemeGenerationRequest,
)
from teg.domain.condensed import GenerationSignals, SummaryFields
from teg.ingestion.catalogues.models import CatalogueCapability, CatalogueStage, CatalogueValueStream
from teg.services.theme_service import ThemeService
from teg.theme.business_needs import _GeneratedBusinessNeeds
from teg.theme.capabilities import CapabilitySelectionItem, CapabilitySelectionResult
from teg.theme.description import _GeneratedDescription, _VsFraming, _VsFramings
from teg.theme.stage_catalogue import StageCatalogue
from teg.theme.stage_selection import BatchedStageSelection, StageSelectionItem, VsStageSelection


def _capability(cap_id: str, name: str, l2_id: str, l2_name: str) -> CatalogueCapability:
    return CatalogueCapability(
        capability_id=cap_id, capability_name=name, capability_description="", level=3, tier="",
        active=True, level_one_id="L1", level_one_name="Manage", level_two_id=l2_id, level_two_name=l2_name,
    )


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
                capabilities=[
                    _capability("CAP-L3-1", "Capture Metrics", "CAP-L2-1", "Reporting"),
                    _capability("CAP-L3-2", "Publish Dashboard", "CAP-L2-1", "Reporting"),
                ],
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
    """Returns the description body/framing/needs/caps/stages based on the requested schema."""

    body_text = "Product Availability:\nPlans: IL, TX, OK"
    framing_text = "The scope of this theme covers reporting and analytics."

    async def complete(self, *, system, user, schema):
        if schema is _GeneratedDescription:
            return _GeneratedDescription(text=self.body_text)
        if schema is _VsFramings:
            return _VsFramings(framings=[_VsFraming(value_stream_id="VSR1", text=self.framing_text)])
        if schema is _GeneratedBusinessNeeds:
            return _GeneratedBusinessNeeds(
                text="Value Stage: Explore Information\n\nBusiness Product Feature: Overall Scope\n1. define CareWay+ metrics"
            )
        if schema is CapabilitySelectionResult:
            return CapabilitySelectionResult(
                capabilities=[CapabilitySelectionItem(capability_id="CAP-L3-1", reason="card needs metrics capture")]
            )
        return BatchedStageSelection(value_streams=[
            VsStageSelection(
                value_stream_id="VSR1",
                selected_stages=[StageSelectionItem(stage_id="VSS1", reason="card centers on exploring information")],
            )
        ])


async def test_generate_one_package_description_and_stages() -> None:
    service = ThemeService(_catalogue(), RoutingFakeLLM(), model_name="gpt-x")
    response = await service.generate(_request())

    assert response.ticket_id == "IDMT-9"
    assert len(response.theme_packages) == 1
    pkg = response.theme_packages[0]
    assert pkg.value_stream_id == "VSR1"
    assert pkg.theme_title == "CP 2027 Guided Health Plans - Discover Business Insights"
    # description = 'Theme Description:' heading + VS framing (batched), then the shared body
    assert pkg.theme_description.startswith("Theme Description:\nThe scope of this theme covers reporting")
    assert "Plans: IL, TX, OK" in pkg.theme_description  # shared body appended
    # stage selection resolved to the governed stage (canonical name), no rank/evidence
    assert [s.stage_id for s in pkg.selected_stages] == ["VSS1"]
    assert pkg.selected_stages[0].stage_name == "Explore Information"
    assert pkg.selected_stages[0].reason.startswith("card centers")
    # business needs is one consolidated text draft (all selected stages)
    assert pkg.business_needs.startswith("Value Stage: Explore Information")
    assert "Business Product Feature: Overall Scope" in pkg.business_needs
    # L3 selected from the governed candidates; L2 derived as the 1-1 parent
    l3 = pkg.l3_capabilities[0].capabilities
    assert [c.capability_id for c in l3] == ["CAP-L3-1"]
    assert l3[0].name == "Capture Metrics"
    l2 = pkg.l2_capabilities[0].capabilities
    assert [(c.capability_id, c.name) for c in l2] == [("CAP-L2-1", "Reporting")]


async def test_invented_stage_id_falls_back_to_full_lifecycle() -> None:
    # An invented id is dropped, but an approved VS must never be left empty -> fall back to
    # the full governed stage list for the architect to trim.
    class InventLLM(RoutingFakeLLM):
        async def complete(self, *, system, user, schema):
            if schema is BatchedStageSelection:
                return BatchedStageSelection(value_streams=[
                    VsStageSelection(
                        value_stream_id="VSR1",
                        selected_stages=[StageSelectionItem(stage_id="NOT-A-STAGE", reason="r")],
                    )
                ])
            return await super().complete(system=system, user=user, schema=schema)

    service = ThemeService(_catalogue(), InventLLM())
    pkg = (await service.generate(_request())).theme_packages[0]
    assert [s.stage_id for s in pkg.selected_stages] == ["VSS1", "VSS2"]  # full list, none invented


async def test_broad_or_unclear_falls_back_to_full_lifecycle() -> None:
    class BroadLLM(RoutingFakeLLM):
        async def complete(self, *, system, user, schema):
            if schema is BatchedStageSelection:
                return BatchedStageSelection(value_streams=[
                    VsStageSelection(value_stream_id="VSR1")  # no picks -> full-list fallback
                ])
            return await super().complete(system=system, user=user, schema=schema)

    pkg = (await ThemeService(_catalogue(), BroadLLM()).generate(_request())).theme_packages[0]
    assert [s.stage_id for s in pkg.selected_stages] == ["VSS1", "VSS2"]  # never empty
