export type ConfidenceLevel = 'high' | 'medium' | 'low';

export type RecordStatus = 'auto_committed' | 'needs_review' | 'human_corrected' | 'flagged_conflict';

export type IngestionStatus = 'completed' | 'processing' | 'queued' | 'failed';

export interface ExtractedField {
  id: string;
  name: string;
  value: string;
  originalValue?: string;
  confidence: number; // 0 - 100
  confidenceLevel: ConfidenceLevel;
  sourceDocument: string;
  sourcePage?: number;
  sourceSection?: string;
  sourceExcerpt: string;
  aiReasoning: string;
  isCorrected?: boolean;
  isApproved?: boolean;
  fieldType: 'text' | 'number' | 'dimension' | 'electrical' | 'boolean' | 'enum';
}

export interface FieldCandidate {
  value: any;
  source_id: string;
  trust_tier: number;
  raw_excerpt: string;
}

export interface FieldConflict {
  id: string;
  product_id: string;
  field_name: string;
  candidates: FieldCandidate[];
  resolution: string;
  resolution_reasoning: string;
  resolved_confidence: number;
}

export interface FieldAuditEntry {
  id: string;
  timestamp: string;
  fieldId: string;
  fieldName: string;
  previousValue: string;
  newValue: string;
  changedBy: string;
  changeType: 'manual_override' | 'verified_approval' | 'revert' | 'ai_initial_extraction' | 'batch_sync';
  confidenceBefore: number;
  confidenceAfter: number;
  reason?: string;
  sourceRef?: string;
}

export interface ProductRecord {
  id: string;
  sku: string;
  name: string;
  brand: string;
  category: string;
  confidence: number; // 0 - 100
  confidenceLevel: ConfidenceLevel;
  status: RecordStatus;
  lastUpdated: string;
  createdAt?: string;
  sourceDocument: string;
  fieldsCount: number;
  fieldsReviewedCount: number;
  fields: ExtractedField[];
  imageUrl?: string;
  specsSummary: string;
  conflictsSummary?: string;
  auditLog?: FieldAuditEntry[];
}

export interface IngestionSource {
  id: string;
  name: string;
  fileName: string;
  fileType: 'PDF Datasheet' | 'CSV Batch' | 'Supplier API' | 'Web Scraper' | 'CAD Metadata';
  fileSize: string;
  recordsCount: number;
  extractedFieldsCount: number;
  status: IngestionStatus;
  avgConfidence: number;
  category: string;
  timestamp: string;
  processingTimeSec?: number;
  aiModelUsed: string;
}

export interface CategoryOverview {
  id: string;
  name: string;
  iconName: string;
  totalRecords: number;
  validatedRecords: number;
  needsReviewCount: number;
  avgConfidence: number;
  accentColor: 'orange' | 'charcoal' | 'cream';
}

export type ActiveTab = 'dashboard' | 'review_queue' | 'field_inspector' | 'catalog' | 'sources' | 'settings' | 'ocr' | 'quality_dashboard' | 'copilot';
