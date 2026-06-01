"""Unit tests for the deferred recognition dispatch + merge logic.

These use lightweight stub classifier adapters so the dispatch/merge behavior
is exercised without onnxruntime or real ONNX artifacts. The ONNX adapter
itself is covered by the classifier-metadata runtime tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from reposcan_contracts.inference import AttributePredictions, BoundingBox, VehicleDetection
from reposcan_inference.deferred_recognition import DeferredRecognitionRunner, _RerankHead


@dataclass
class StubClassifier:
    """Returns a fixed AttributePredictions per call, ignoring the crop.

    `by_label` lets a stub return different predictions keyed on the incoming
    detection's class_label, so re-rank behavior can be asserted per crop.
    """

    default: AttributePredictions
    by_label: dict[str, AttributePredictions] | None = None

    def predict(
        self,
        frame,
        vehicle_detections: Sequence[VehicleDetection],
    ) -> list[AttributePredictions]:
        out = []
        for det in vehicle_detections:
            key = det.class_label
            if self.by_label and key in self.by_label:
                out.append(self.by_label[key])
            else:
                out.append(self.default)
        return out


def _det(label: str) -> VehicleDetection:
    return VehicleDetection(
        bbox=BoundingBox(x=0.0, y=0.0, w=10.0, h=10.0),
        confidence=0.9,
        class_label=label,
    )


def _mm(make: str, conf: float = 0.8) -> AttributePredictions:
    return AttributePredictions(make=make, make_confidence=conf)


def test_no_detections_returns_empty():
    runner = DeferredRecognitionRunner(make_model=StubClassifier(default=_mm("toyota_camry")))
    assert runner.recognize(frame=object(), vehicle_detections=[]) == []


def test_make_model_only_passthrough():
    runner = DeferredRecognitionRunner(make_model=StubClassifier(default=_mm("toyota_camry", 0.77)))
    preds = runner.recognize(frame=object(), vehicle_detections=[_det("a")])
    assert len(preds) == 1
    assert preds[0].make == "toyota_camry"
    assert preds[0].make_confidence == 0.77


def test_rerank_overrides_only_triggered_class():
    # Primary predicts jeep_grand_cherokee for det "a" (a trigger) and
    # toyota_camry for det "b" (not a trigger). The Jeep head should only
    # rewrite det "a".
    make_model = StubClassifier(
        default=_mm("toyota_camry"),
        by_label={"a": _mm("jeep_grand_cherokee", 0.51), "b": _mm("toyota_camry", 0.9)},
    )
    jeep_head = _RerankHead(
        name="jeep",
        trigger_classes=frozenset({"jeep_grand_cherokee", "jeep_wrangler"}),
        adapter=StubClassifier(default=_mm("jeep_wrangler", 0.95)),
    )
    runner = DeferredRecognitionRunner(make_model=make_model, rerank_heads=[jeep_head])

    preds = runner.recognize(frame=object(), vehicle_detections=[_det("a"), _det("b")])

    # det "a" got re-ranked to the head's output
    assert preds[0].make == "jeep_wrangler"
    assert preds[0].make_confidence == 0.95
    # det "b" untouched
    assert preds[1].make == "toyota_camry"
    assert preds[1].make_confidence == 0.9


def test_non_trigger_class_skips_rerank():
    make_model = StubClassifier(default=_mm("toyota_camry", 0.6))
    jeep_head = _RerankHead(
        name="jeep",
        trigger_classes=frozenset({"jeep_grand_cherokee"}),
        adapter=StubClassifier(default=_mm("SHOULD_NOT_APPEAR", 1.0)),
    )
    runner = DeferredRecognitionRunner(make_model=make_model, rerank_heads=[jeep_head])
    preds = runner.recognize(frame=object(), vehicle_detections=[_det("a")])
    assert preds[0].make == "toyota_camry"


def test_year_and_color_merge():
    runner = DeferredRecognitionRunner(
        make_model=StubClassifier(default=_mm("honda_accord", 0.82)),
        year=StubClassifier(default=AttributePredictions(year="bucket_2019_2022", year_confidence=0.7)),
        color=StubClassifier(default=AttributePredictions(color="white", color_confidence=0.66)),
    )
    preds = runner.recognize(frame=object(), vehicle_detections=[_det("a")])
    p = preds[0]
    assert p.make == "honda_accord"
    assert p.make_confidence == 0.82
    assert p.year == "bucket_2019_2022"
    assert p.year_confidence == 0.7
    assert p.color == "white"
    assert p.color_confidence == 0.66


def test_rerank_plus_year_color_full_merge():
    make_model = StubClassifier(default=_mm("chevrolet_tahoe", 0.55))
    suv_head = _RerankHead(
        name="gm-fullsize-suv",
        trigger_classes=frozenset({"chevrolet_suburban", "chevrolet_tahoe", "gmc_yukon"}),
        adapter=StubClassifier(default=_mm("chevrolet_suburban", 0.88)),
    )
    runner = DeferredRecognitionRunner(
        make_model=make_model,
        rerank_heads=[suv_head],
        year=StubClassifier(default=AttributePredictions(year="bucket_2015_2018", year_confidence=0.6)),
        color=StubClassifier(default=AttributePredictions(color="black", color_confidence=0.71)),
    )
    p = runner.recognize(frame=object(), vehicle_detections=[_det("a")])[0]
    # re-rank applied
    assert p.make == "chevrolet_suburban"
    assert p.make_confidence == 0.88
    # year/color attached on top of the re-ranked make/model
    assert p.year == "bucket_2015_2018"
    assert p.color == "black"
