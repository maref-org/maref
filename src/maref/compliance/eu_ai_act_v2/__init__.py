"""
EU AI Act Compliance — V2 Engine

Implements full compliance with Regulation (EU) 2024/1689:
- Art.6-7 + Annex III: Risk classification
- Art.9: Risk management system
- Art.11 + Annex IV: Technical documentation
- Art.13 + Art.50: Transparency obligations
- Art.14: Human oversight
- Art.43 + Annex VI/VII: Conformity assessment
- Art.53-55 + Annex XI: GPAI obligations
- Art.17: Quality management system
- Art.20 + Art.73: Incident reporting
- Art.27: Fundamental Rights Impact Assessment
- Art.61: Post-market monitoring
"""

from __future__ import annotations

from maref.compliance.eu_ai_act_v2.accuracy_robustness import (
    AccuracyDeclaration,
    AccuracyManager,
    AccuracyMetricType,
    Art15ComplianceReport,
    CybersecurityAssessment,
    CybersecurityManager,
    FeedbackLoopDetector,
    FeedbackLoopReport,
    RobustnessManager,
    RobustnessReport,
)
from maref.compliance.eu_ai_act_v2.conformity_assessment import (
    CEMarking,
    ConformityAssessmentManager,
    ConformityAssessmentRecord,
    ConformityRoute,
    DeclarationStatus,
    EUDatabaseRegistration,
    EUDeclarationOfConformity,
    SubstantialModificationType,
)
from maref.compliance.eu_ai_act_v2.data_governance import (
    BiasDetectionReport,
    DataGovernanceManager,
    DatasetGovernanceRecord,
    DatasetQualityMetrics,
    SpecialCategoryAssessment,
)
from maref.compliance.eu_ai_act_v2.engine import (
    EUAIComplianceEngineV2,
    EUAIComplianceSummary,
)
from maref.compliance.eu_ai_act_v2.fria import (
    FRIAManager,
    FRIAReport,
    FRIAScope,
    FundamentalRight,
    FundamentalRightAssessment,
    RiskRating,
)
from maref.compliance.eu_ai_act_v2.gpai import (
    CopyrightPolicy,
    DownstreamTransparency,
    EnergyEfficiencyReport,
    EvalType,
    GPAIComplianceManager,
    GPAIStatus,
    ModelEvaluation,
    PostMarketMonitoringGPAI,
    SystemicRiskAssessment,
    TrainingDataSummary,
)
from maref.compliance.eu_ai_act_v2.gpai import (
    TechnicalDocumentation as GPAITechnicalDocumentation,
)
from maref.compliance.eu_ai_act_v2.qms import (
    QMSAuditRecord,
    QMSDocument,
    QMSManager,
    QualityPolicy,
)
from maref.compliance.eu_ai_act_v2.human_oversight import (
    HumanOversightAssessment,
    HumanOversightBridge,
    OversightCapability,
    OversightCapabilityStatus,
    OversightMode,
)
from maref.compliance.eu_ai_act_v2.incident_reporting import (
    CorrectiveAction,
    IncidentManager,
    IncidentRecord,
    IncidentSeverity,
    IncidentStatus,
)
from maref.compliance.eu_ai_act_v2.post_market_monitoring import (
    PMMManager,
    PMMObservation,
    PMMPlan,
    PMMTrendAnalysis,
    PeriodicReport,
)
from maref.compliance.eu_ai_act_v2.record_keeping import (
    AIActLogEntry,
    AIActLogger,
    RegulatoryLogExporter,
    RetentionPolicy,
)
from maref.compliance.eu_ai_act_v2.risk_classifier import (
    AnnexIIICategory,
    ClassificationDetail,
    ExemptionReason,
    GPAIThreshold,
    RiskClassifier,
    RiskLevel,
)
from maref.compliance.eu_ai_act_v2.risk_management import (
    RiskAssessment,
    RiskLikelihood,
    RiskManagementLifecycleState,
    RiskManagementSystem,
    RiskMitigationMeasure,
    RiskSeverity,
)
from maref.compliance.eu_ai_act_v2.technical_docs import (
    DataGovernance,
    DevelopmentMethodology,
    PostMarketMonitoringPlan,
    SystemArchitecture,
    TechnicalDocumentation,
    ValidationProcedure,
)
from maref.compliance.eu_ai_act_v2.transparency import (
    AIContentWatermark,
    ChatbotDisclosure,
    DeepfakeDisclosure,
    EmotionalRecognitionDisclosure,
    EndUserTransparency,
    InstructionForUse,
    TransparencyDeclaration,
    TransparencyManager,
)

__all__ = [
    "AccuracyDeclaration",
    "AccuracyManager",
    "AccuracyMetricType",
    "Art15ComplianceReport",
    "CybersecurityAssessment",
    "CybersecurityManager",
    "FeedbackLoopDetector",
    "FeedbackLoopReport",
    "RobustnessManager",
    "RobustnessReport",
    "BiasDetectionReport",
    "DataGovernanceManager",
    "DatasetGovernanceRecord",
    "DatasetQualityMetrics",
    "SpecialCategoryAssessment",
    "AIActLogEntry",
    "AIActLogger",
    "RegulatoryLogExporter",
    "RetentionPolicy",
    "AnnexIIICategory",
    "ClassificationDetail",
    "ExemptionReason",
    "GPAIThreshold",
    "RiskClassifier",
    "RiskLevel",
    "RiskSeverity",
    "RiskLikelihood",
    "RiskManagementLifecycleState",
    "RiskManagementSystem",
    "RiskAssessment",
    "RiskMitigationMeasure",
    "DataGovernance",
    "DevelopmentMethodology",
    "PostMarketMonitoringPlan",
    "SystemArchitecture",
    "TechnicalDocumentation",
    "ValidationProcedure",
    "CorrectiveAction",
    "IncidentManager",
    "IncidentRecord",
    "IncidentSeverity",
    "IncidentStatus",
    "InstructionForUse",
    "ChatbotDisclosure",
    "DeepfakeDisclosure",
    "EmotionalRecognitionDisclosure",
    "AIContentWatermark",
    "TransparencyDeclaration",
    "EndUserTransparency",
    "TransparencyManager",
    "OversightCapability",
    "OversightMode",
    "OversightCapabilityStatus",
    "HumanOversightAssessment",
    "HumanOversightBridge",
    "ConformityRoute",
    "DeclarationStatus",
    "SubstantialModificationType",
    "ConformityAssessmentRecord",
    "EUDeclarationOfConformity",
    "CEMarking",
    "EUDatabaseRegistration",
    "ConformityAssessmentManager",
    "GPAIStatus",
    "EvalType",
    "CopyrightPolicy",
    "TrainingDataSummary",
    "DownstreamTransparency",
    "GPAITechnicalDocumentation",
    "SystemicRiskAssessment",
    "ModelEvaluation",
    "PostMarketMonitoringGPAI",
    "EnergyEfficiencyReport",
    "GPAIComplianceManager",
    "QMSAuditRecord",
    "QMSDocument",
    "QMSManager",
    "QualityPolicy",
    "FRIAManager",
    "FRIAReport",
    "FRIAScope",
    "FundamentalRight",
    "FundamentalRightAssessment",
    "RiskRating",
    "EUAIComplianceEngineV2",
    "EUAIComplianceSummary",
    "PeriodicReport",
    "PMMManager",
    "PMMObservation",
    "PMMPlan",
    "PMMTrendAnalysis",
]
