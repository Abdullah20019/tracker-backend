from typing import Any, Literal
from pydantic import BaseModel, Field


class TrackingEvent(BaseModel):
    status: str
    location: str | None = None
    timestamp: str | None = None
    details: str | None = None


class ProgressStep(BaseModel):
    label: str
    active: bool = False


class ShipmentDetails(BaseModel):
    agentReferenceNumber: str | None = None
    trackingCode: str | None = None
    origin: str | None = None
    destination: str | None = None
    bookingDate: str | None = None
    shipper: str | None = None
    consignee: str | None = None
    pieces: str | None = None
    signedForBy: str | None = None
    deliveryType: str | None = None
    reason: str | None = None
    senderAddress: str | None = None
    senderPhone: str | None = None
    receiverAddress: str | None = None
    receiverPhone: str | None = None


class TrackingResult(BaseModel):
    courier: str
    trackingNumber: str
    success: bool
    status: str | None = None
    location: str | None = None
    timestamp: str | None = None
    events: list[TrackingEvent] = Field(default_factory=list)
    error: str | None = None
    strategy: str | None = None
    cached: bool = False
    shipmentDetails: ShipmentDetails | None = None
    customerMessage: str | None = None
    progressSteps: list[ProgressStep] = Field(default_factory=list)


class TrackRequest(BaseModel):
    courier: str | None = None
    trackingNumber: str = Field(min_length=5, max_length=64)
    autoDetect: bool = False


class BulkTrackRequest(BaseModel):
    courier: str | None = None
    trackingNumbers: list[str] = Field(min_length=1, max_length=20)
    autoDetect: bool = False


class CourierDescriptor(BaseModel):
    id: str
    name: str
    enabled: bool
    supportsBulk: bool
    strategyPriority: list[str]


class InternalCourierStatus(BaseModel):
    id: str
    metrics: dict[str, Any]
    enabled: bool
    strategies: list[str]


class StrategyName:
    HTTP = "http"
    HTML = "html"
    LIGHTPANDA = "lightpanda"
    EDGE = "edge"
