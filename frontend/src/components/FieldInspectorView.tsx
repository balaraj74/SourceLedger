import React, { useState, useMemo, useEffect } from 'react';
import { 
  ArrowLeft, 
  CheckCircle2, 
  AlertTriangle, 
  FileText, 
  Edit3, 
  Check, 
  X, 
  Sparkles, 
  ExternalLink, 
  ChevronLeft, 
  ChevronRight, 
  ShieldCheck,
  Search,
  BookOpen,
  History,
  ListFilter,
  Info,
  GitBranch,
  ArrowRight
} from 'lucide-react';
import { ProductRecord, ExtractedField } from '../types';
import { CircularProgress } from './CircularProgress';
import { StatusPill } from './StatusPill';
import { ProductFieldHistoryTab } from './ProductFieldHistoryTab';
import { getProductRelationships, ProductRelationshipData } from '../lib/api';

interface FieldInspectorViewProps {
  product: ProductRecord;
  products: ProductRecord[];
  onSelectProduct: (product: ProductRecord) => void;
  onUpdateField: (productId: string, fieldId: string, newValue: string, isApproved: boolean) => void;
  onApproveAllFields: (productId: string) => void;
  onBackToDashboard: () => void;
}

export const FieldInspectorView: React.FC<FieldInspectorViewProps> = ({
  product,
  products,
  onSelectProduct,
  onUpdateField,
  onApproveAllFields,
  onBackToDashboard
}) => {
  const [editingFieldId, setEditingFieldId] = useState<string | null>(null);
  const [editedValue, setEditedValue] = useState<string>('');
  const [activeInspectorTab, setActiveInspectorTab] = useState<'fields' | 'history' | 'document_preview'>('fields');
  const [filterConfidence, setFilterConfidence] = useState<'all' | 'needs_review' | 'high'>('all');
  const [relationships, setRelationships] = useState<ProductRelationshipData[]>([]);

  useEffect(() => {
    if (product && product.sku) {
      getProductRelationships(product.sku).then(setRelationships).catch(() => setRelationships([]));
    }
  }, [product?.sku]);

  if (!product) {
    return (
      <div className="bg-white/70 backdrop-blur-2xl rounded-3xl p-12 text-center border border-white/80 ring-1 ring-white/50 shadow-[0_8px_32px_rgba(26,23,21,0.04)] max-w-lg mx-auto my-12">
        <div className="w-16 h-16 rounded-2xl bg-[#FAF4EB] text-[#E8622C] flex items-center justify-center mx-auto mb-4 border border-[#DFCDBC]/50">
          <Info className="w-8 h-8" />
        </div>
        <h3 className="font-didone font-bold text-2xl text-[#191715]">
          No Product Selected
        </h3>
        <p className="text-xs text-[#5C554D] mt-2 leading-relaxed">
          Ingest a new datasheet or select a product record from your catalog to inspect its extracted attributes and field provenance.
        </p>
        <button
          onClick={onBackToDashboard}
          className="mt-6 px-5 py-2.5 rounded-full bg-[#E8622C] text-white text-xs font-bold shadow-md shadow-[#E8622C]/20 hover:bg-[#D45320] transition-all cursor-pointer"
        >
          Return to Dashboard
        </button>
      </div>
    );
  }

  const currentIndex = products.findIndex(p => p.id === product.id);
  const prevProduct = currentIndex > 0 ? products[currentIndex - 1] : null;
  const nextProduct = currentIndex < products.length - 1 ? products[currentIndex + 1] : null;

  const handleStartEdit = (field: ExtractedField) => {
    setEditingFieldId(field.id);
    setEditedValue(field.value);
  };

  const handleSaveEdit = (fieldId: string) => {
    onUpdateField(product.id, fieldId, editedValue, true);
    setEditingFieldId(null);
  };

  const handleCancelEdit = () => {
    setEditingFieldId(null);
  };

  const handleRevertField = (fieldId: string, valueToRestore: string) => {
    onUpdateField(product.id, fieldId, valueToRestore, true);
  };

  const [selectedCategory, setSelectedCategory] = useState<string>('all');

  const getFieldCategory = (fieldName: string): 'identity' | 'descriptions' | 'features' | 'specs' | 'logistics' => {
    const nameLower = fieldName.toLowerCase();
    if (['mfg_part_num', 'part_number', 'manufacturer', 'brand', 'trade_name', 'dept', 'class', 'fine', 'classpath', 'product_name'].some(k => nameLower.includes(k))) {
      return 'identity';
    }
    if (['desc', 'description', 'title', 'marketing', 'short_desc', 'long_desc', 'invoice_desc', 'mobile_desc'].some(k => nameLower.includes(k))) {
      return 'descriptions';
    }
    if (nameLower.includes('feature') || nameLower.includes('selling')) {
      return 'features';
    }
    if (['url', 'image', 'sds', 'manual', 'pdf', 'drawing', 'rohs', 'country', 'upc', 'ean', 'unspsc', 'length', 'width', 'height', 'weight'].some(k => nameLower.includes(k))) {
      return 'logistics';
    }
    return 'specs';
  };

  const filteredFields = product.fields.filter(field => {
    if (filterConfidence === 'needs_review' && field.confidence >= 85) return false;
    if (filterConfidence === 'high' && field.confidence < 85) return false;
    if (selectedCategory !== 'all') {
      const cat = getFieldCategory(field.name);
      if (cat !== selectedCategory) return false;
    }
    return true;
  });

  const auditCount = product.auditLog ? product.auditLog.length : 4;

  return (
    <div className="space-y-6 pb-16">
      {/* Top Breadcrumb & Product Navigation Bar - Frosted Glass Card */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-white/70 backdrop-blur-xl p-4 rounded-3xl border border-white/80 ring-1 ring-white/50 shadow-[0_8px_32px_rgba(26,23,21,0.04)]">
        <div className="flex items-center gap-3">
          <button
            onClick={onBackToDashboard}
            className="p-2.5 rounded-2xl bg-white/60 hover:bg-white/90 backdrop-blur-md text-[#191715] border border-white/70 shadow-2xs transition-all cursor-pointer"
            title="Back to Dashboard"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-[#8C8276]">
                Field Inspector
              </span>
              <span className="text-[#8C8276]">•</span>
              <span className="text-xs font-semibold text-[#E8622C]">
                {product.brand}
              </span>
            </div>
            <h1 className="font-didone font-bold text-base sm:text-xl text-[#191715] leading-tight">
              {product.name}
            </h1>
          </div>
        </div>

        {/* Product Switcher buttons */}
        <div className="flex items-center gap-2">
          <button
            disabled={!prevProduct}
            onClick={() => prevProduct && onSelectProduct(prevProduct)}
            className="p-2 rounded-xl bg-white/50 hover:bg-white/80 backdrop-blur-md disabled:opacity-40 disabled:cursor-not-allowed text-[#191715] text-xs font-bold flex items-center gap-1 border border-white/60 shadow-2xs transition-colors cursor-pointer"
            title="Previous Product"
          >
            <ChevronLeft className="w-4 h-4" />
            <span className="hidden sm:inline">Prev Record</span>
          </button>
          <span className="text-xs font-bold text-[#8C8276] px-2 font-mono">
            {currentIndex + 1} / {products.length}
          </span>
          <button
            disabled={!nextProduct}
            onClick={() => nextProduct && onSelectProduct(nextProduct)}
            className="p-2 rounded-xl bg-white/50 hover:bg-white/80 backdrop-blur-md disabled:opacity-40 disabled:cursor-not-allowed text-[#191715] text-xs font-bold flex items-center gap-1 border border-white/60 shadow-2xs transition-colors cursor-pointer"
            title="Next Product"
          >
            <span className="hidden sm:inline">Next Record</span>
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Main Product Header Glass Card */}
      <div className="bg-white/70 backdrop-blur-2xl rounded-3xl p-6 sm:p-8 border border-white/80 ring-1 ring-white/50 shadow-[0_8px_32px_rgba(26,23,21,0.05)] relative overflow-hidden">
        <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6">
          {/* Left: Product Meta & Summary */}
          <div className="space-y-3 flex-1">
            <div className="flex flex-wrap items-center gap-2.5">
              <span className="text-xs font-mono font-bold px-2.5 py-1 rounded-md bg-white/60 backdrop-blur-md text-[#191715] border border-white/70 shadow-2xs">
                SKU: {product.sku}
              </span>
              <span className="text-xs font-semibold px-2.5 py-1 rounded-md bg-white/60 backdrop-blur-md text-[#5C554D] border border-white/70 shadow-2xs">
                {product.category}
              </span>
              <StatusPill type="status" status={product.status} size="md" />
            </div>

            <h2 className="font-display font-black text-2xl sm:text-3xl text-[#191715] tracking-tight">
              {product.name}
            </h2>

            <p className="text-sm text-[#5C554D] leading-relaxed max-w-2xl">
              {product.specsSummary}
            </p>

            <div className="flex flex-wrap items-center gap-4 pt-2 text-xs text-[#8C8276]">
              <span className="flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5 text-[#E8622C]" />
                Source: <span className="font-semibold text-[#191715]">{product.sourceDocument}</span>
              </span>
              <span>•</span>
              <span>Total Fields Extracted: <strong className="text-[#191715]">{product.fields.length}</strong></span>
              <span>•</span>
              <span>Last Analyzed: <strong className="text-[#191715]">{product.lastUpdated}</strong></span>
            </div>

            {/* Conflict Alert Banner if present */}
            {product.conflictsSummary && (
              <div className="mt-3 p-3.5 rounded-2xl bg-[#FEF7ED]/85 backdrop-blur-md border border-[#FED7AA] flex items-start gap-3 shadow-xs">
                <AlertTriangle className="w-5 h-5 text-[#E8622C] shrink-0 mt-0.5" />
                <div>
                  <h4 className="text-xs font-bold text-[#9A3412]">AI Conflict Alert</h4>
                  <p className="text-xs text-[#9A3412]/90 mt-0.5">
                    {product.conflictsSummary}
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Right: Overall Confidence Ring & Actions */}
          <div className="flex flex-col sm:flex-row items-center gap-6 bg-white/60 backdrop-blur-xl p-5 rounded-3xl border border-white/70 shadow-sm shrink-0 self-stretch lg:self-auto justify-between sm:justify-center">
            <div className="flex flex-col items-center">
              <CircularProgress
                value={product.confidence}
                size={96}
                strokeWidth={9}
                color={product.confidence >= 85 ? 'orange' : product.confidence >= 65 ? 'charcoal' : 'amber'}
                sublabel="Overall"
              />
              <span className="text-[11px] font-bold text-[#8C8276] mt-2">
                Catalog Confidence
              </span>
            </div>

            <div className="flex flex-col gap-2 w-full sm:w-auto">
              <button
                onClick={() => onApproveAllFields(product.id)}
                className="px-4 py-2.5 rounded-full bg-gradient-to-r from-[#E8622C] to-[#D45320] hover:scale-[1.02] text-white text-xs font-bold flex items-center justify-center gap-2 shadow-md shadow-[#E8622C]/25 border border-white/20 transition-all cursor-pointer"
              >
                <CheckCircle2 className="w-4 h-4" />
                <span>Approve All Fields</span>
              </button>
              <button
                onClick={() => setActiveInspectorTab(activeInspectorTab === 'history' ? 'fields' : 'history')}
                className={`px-4 py-2.5 rounded-full text-xs font-bold flex items-center justify-center gap-2 border shadow-2xs transition-all cursor-pointer ${
                  activeInspectorTab === 'history'
                    ? 'bg-[#191715] text-white border-[#191715]'
                    : 'bg-white/70 hover:bg-white/90 backdrop-blur-md text-[#191715] border-white/70'
                }`}
              >
                <History className="w-4 h-4 text-[#E8622C]" />
                <span>View Field History ({auditCount})</span>
              </button>

            </div>
          </div>
        </div>
      </div>

      {/* Primary Inspector Mode Tab Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#1A1A1A]/10 pb-1">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveInspectorTab('fields')}
            className={`px-4 py-2.5 rounded-2xl font-display font-bold text-xs sm:text-sm flex items-center gap-2 transition-all cursor-pointer ${
              activeInspectorTab === 'fields'
                ? 'bg-[#191715] text-white shadow-md'
                : 'bg-white/60 hover:bg-white text-[#5C554D] border border-white/70'
            }`}
          >
            <ListFilter className="w-4 h-4" />
            <span>Extracted Attributes</span>
            <span className={`px-2 py-0.5 rounded-full text-[10px] font-mono ${
              activeInspectorTab === 'fields' ? 'bg-white/20 text-white' : 'bg-black/5 text-[#5C554D]'
            }`}>
              {product.fields.length}
            </span>
          </button>

          <button
            onClick={() => setActiveInspectorTab('history')}
            className={`px-4 py-2.5 rounded-2xl font-display font-bold text-xs sm:text-sm flex items-center gap-2 transition-all cursor-pointer ${
              activeInspectorTab === 'history'
                ? 'bg-[#E8622C] text-white shadow-md shadow-[#E8622C]/25'
                : 'bg-white/60 hover:bg-white text-[#5C554D] border border-white/70'
            }`}
          >
            <History className="w-4 h-4" />
            <span>History & Audit Log</span>
            <span className={`px-2 py-0.5 rounded-full text-[10px] font-mono ${
              activeInspectorTab === 'history' ? 'bg-white/25 text-white font-bold' : 'bg-[#E8622C]/10 text-[#E8622C] font-bold'
            }`}>
              {auditCount}
            </span>
          </button>

          <button
            onClick={() => setActiveInspectorTab('document_preview')}
            className={`px-4 py-2.5 rounded-2xl font-display font-bold text-xs sm:text-sm flex items-center gap-2 transition-all cursor-pointer ${
              activeInspectorTab === 'document_preview'
                ? 'bg-[#191715] text-white shadow-md'
                : 'bg-white/60 hover:bg-white text-[#5C554D] border border-white/70'
            }`}
          >
            <BookOpen className="w-4 h-4" />
            <span className="hidden sm:inline">Source Datasheet Document</span>
            <span className="sm:hidden">Document</span>
          </button>
        </div>

        {activeInspectorTab === 'fields' && (
          <span className="text-xs text-[#8C8276] font-medium hidden md:inline">
            Showing {filteredFields.length} of {product.fields.length} extracted attributes
          </span>
        )}
      </div>

      {/* Knowledge Graph Related Products Panel (Phase 8) */}
      {activeInspectorTab === 'fields' && relationships.length > 0 && (
        <div className="bg-white/70 backdrop-blur-2xl rounded-3xl p-5 border border-white/80 shadow-[0_8px_32px_rgba(26,23,21,0.04)] space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm font-bold text-[#191715] font-display">
              <GitBranch className="w-4.5 h-4.5 text-[#E8622C]" />
              <span>Product Knowledge Graph — Linked Variants & Substitutes</span>
            </div>
            <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-[#E8622C]/10 text-[#E8622C] border border-[#E8622C]/20">
              {relationships.length} Graph Relationships Detected
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {relationships.map((rel, idx) => {
              const relatedSku = rel.source_sku === product.sku ? rel.target_sku : rel.source_sku;
              const relatedProd = products.find(p => p.sku === relatedSku || p.name === relatedSku);

              return (
                <div
                  key={idx}
                  onClick={() => relatedProd && onSelectProduct(relatedProd)}
                  className={`p-3.5 rounded-2xl bg-white/80 backdrop-blur-md border border-white/80 shadow-2xs space-y-2 transition-all ${
                    relatedProd ? 'hover:border-[#E8622C] hover:shadow-md cursor-pointer' : ''
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md bg-[#E8622C]/10 text-[#E8622C] border border-[#E8622C]/20">
                      {rel.relationship_type.replace('_', ' ')}
                    </span>
                    <span className="text-[10px] font-mono font-bold text-[#8C8276]">
                      {rel.confidence}% Trust
                    </span>
                  </div>

                  <div className="font-display font-bold text-sm text-[#191715] flex items-center justify-between">
                    <span>{relatedSku}</span>
                    {relatedProd && <ArrowRight className="w-3.5 h-3.5 text-[#E8622C]" />}
                  </div>

                  <p className="text-xs text-[#5C554D] leading-relaxed line-clamp-2">
                    {rel.reasoning}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Filter Tabs for Fields (only shown in Extracted Attributes tab) */}
      {activeInspectorTab === 'fields' && (
        <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
          {/* Category Tabs */}
          <div className="flex items-center gap-1.5 bg-white/60 backdrop-blur-md p-1.5 rounded-2xl border border-white/70 shadow-2xs overflow-x-auto">
            <button
              onClick={() => setSelectedCategory('all')}
              className={`px-3 py-1 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                selectedCategory === 'all' ? 'bg-[#191715] text-white shadow-xs' : 'text-[#5C554D] hover:text-[#191715]'
              }`}
            >
              All ({product.fields.length})
            </button>
            <button
              onClick={() => setSelectedCategory('identity')}
              className={`px-3 py-1 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                selectedCategory === 'identity' ? 'bg-[#191715] text-white shadow-xs' : 'text-[#5C554D] hover:text-[#191715]'
              }`}
            >
              Identity & Taxonomy
            </button>
            <button
              onClick={() => setSelectedCategory('descriptions')}
              className={`px-3 py-1 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                selectedCategory === 'descriptions' ? 'bg-[#191715] text-white shadow-xs' : 'text-[#5C554D] hover:text-[#191715]'
              }`}
            >
              Descriptions
            </button>
            <button
              onClick={() => setSelectedCategory('features')}
              className={`px-3 py-1 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                selectedCategory === 'features' ? 'bg-[#191715] text-white shadow-xs' : 'text-[#5C554D] hover:text-[#191715]'
              }`}
            >
              Item Features
            </button>
            <button
              onClick={() => setSelectedCategory('specs')}
              className={`px-3 py-1 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                selectedCategory === 'specs' ? 'bg-[#191715] text-white shadow-xs' : 'text-[#5C554D] hover:text-[#191715]'
              }`}
            >
              Technical Specs
            </button>
            <button
              onClick={() => setSelectedCategory('logistics')}
              className={`px-3 py-1 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                selectedCategory === 'logistics' ? 'bg-[#191715] text-white shadow-xs' : 'text-[#5C554D] hover:text-[#191715]'
              }`}
            >
              Logistics & Assets
            </button>
          </div>

          {/* Confidence Filters */}
          <div className="flex items-center gap-2 bg-white/60 backdrop-blur-md p-1.5 rounded-full border border-white/70 shadow-2xs">
            <button
              onClick={() => setFilterConfidence('all')}
              className={`px-3.5 py-1.5 rounded-full text-xs font-bold transition-all cursor-pointer ${
                filterConfidence === 'all'
                  ? 'bg-[#191715] text-white shadow-xs'
                  : 'text-[#5C554D] hover:text-[#191715]'
              }`}
            >
              All Confidence
            </button>
            <button
              onClick={() => setFilterConfidence('needs_review')}
              className={`px-3.5 py-1.5 rounded-full text-xs font-bold transition-all cursor-pointer ${
                filterConfidence === 'needs_review'
                  ? 'bg-[#E8622C] text-white shadow-xs'
                  : 'text-[#5C554D] hover:text-[#191715]'
              }`}
            >
              Needs Review ({product.fields.filter(f => f.confidence < 85).length})
            </button>
            <button
              onClick={() => setFilterConfidence('high')}
              className={`px-3.5 py-1.5 rounded-full text-xs font-bold transition-all cursor-pointer ${
                filterConfidence === 'high'
                  ? 'bg-[#191715] text-white shadow-xs'
                  : 'text-[#5C554D] hover:text-[#191715]'
              }`}
            >
              High Confidence ({product.fields.filter(f => f.confidence >= 85).length})
            </button>
          </div>
        </div>
      )}


      {/* Main View Mode: Extracted Fields vs History vs Original Document Preview */}
      {activeInspectorTab === 'history' ? (
        <ProductFieldHistoryTab
          product={product}
          onRevertField={handleRevertField}
        />
      ) : activeInspectorTab === 'fields' ? (
        <div className="space-y-4">
          {filteredFields.map((field) => {
            const isEditing = editingFieldId === field.id;

            return (
              <div
                key={field.id}
                className="bg-white/70 backdrop-blur-2xl rounded-3xl p-6 border border-white/80 ring-1 ring-white/50 shadow-[0_8px_32px_rgba(26,23,21,0.04)] transition-all hover:border-[#E8622C]/40"
              >
                <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6">
                  {/* Left & Middle: Field Name, Value, Excerpt, Reasoning */}
                  <div className="flex-1 space-y-4 w-full">
                    {/* Field Header */}
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2.5">
                        <span className="font-display font-bold text-base text-[#191715]">
                          {field.name}
                        </span>
                        <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md bg-white/60 backdrop-blur-md text-[#8C8276] border border-white/70 shadow-2xs">
                          {field.fieldType}
                        </span>
                        {field.isApproved && (
                          <span className="inline-flex items-center gap-1 text-xs font-bold text-[#1F8A53] bg-[#EAF5EE]/80 backdrop-blur-md px-2.5 py-0.5 rounded-full border border-[#1F8A53]/20 shadow-2xs">
                            <Check className="w-3 h-3" /> Approved
                          </span>
                        )}
                        {field.isCorrected && (
                          <span className="inline-flex items-center gap-1 text-xs font-bold text-[#E8622C] bg-[#FDF2EC]/80 backdrop-blur-md px-2.5 py-0.5 rounded-full border border-[#E8622C]/20 shadow-2xs">
                            <Edit3 className="w-3 h-3" /> Manually Corrected
                          </span>
                        )}
                      </div>

                      <StatusPill
                        type="confidence"
                        confidenceScore={field.confidence}
                        label={field.confidence >= 85 ? 'High (Auto-Commit)' : field.confidence >= 65 ? 'Medium (Review)' : 'Conflict / Low'}
                        size="sm"
                      />
                    </div>

                    {/* Extracted Value Display / Edit Form - Frosted Sub-card */}
                    <div className="p-3.5 rounded-2xl bg-white/60 backdrop-blur-md border border-white/80 shadow-2xs flex items-center justify-between gap-4">
                      <div className="flex-1">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-[#8C8276] block mb-1">
                          Canonical Catalog Value
                        </span>
                        {isEditing ? (
                          <div className="flex items-center gap-2">
                            <input
                              type="text"
                              value={editedValue}
                              onChange={(e) => setEditedValue(e.target.value)}
                              className="w-full bg-white/90 backdrop-blur-md px-3 py-1.5 text-sm font-semibold text-[#191715] rounded-xl border border-[#E8622C] focus:ring-2 focus:ring-[#E8622C]/20 outline-hidden"
                              autoFocus
                            />
                            <button
                              onClick={() => handleSaveEdit(field.id)}
                              className="px-3 py-1.5 rounded-xl bg-[#E8622C] text-white text-xs font-bold flex items-center gap-1 cursor-pointer shadow-xs"
                            >
                              <Check className="w-3.5 h-3.5" /> Save
                            </button>
                            <button
                              onClick={handleCancelEdit}
                              className="px-3 py-1.5 rounded-xl bg-white/80 text-[#5C554D] text-xs font-bold border border-white/80 cursor-pointer shadow-2xs"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        ) : (
                          <span className="font-display font-bold text-base sm:text-lg text-[#191715]">
                            {field.value}
                          </span>
                        )}
                      </div>

                      {!isEditing && (
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => handleStartEdit(field)}
                            className="p-2 rounded-xl bg-white/70 hover:bg-white/95 backdrop-blur-md text-[#5C554D] hover:text-[#191715] border border-white/80 shadow-2xs text-xs font-bold flex items-center gap-1.5 transition-colors cursor-pointer"
                            title="Edit / Override Value"
                          >
                            <Edit3 className="w-3.5 h-3.5 text-[#E8622C]" />
                            <span className="hidden sm:inline">Override</span>
                          </button>
                          <button
                            onClick={() => onUpdateField(product.id, field.id, field.value, true)}
                            className="p-2 rounded-xl bg-[#191715] hover:bg-[#E8622C] text-white text-xs font-bold flex items-center gap-1.5 shadow-xs transition-colors cursor-pointer"
                            title="Confirm & Approve"
                          >
                            <Check className="w-3.5 h-3.5" />
                            <span className="hidden sm:inline">Approve</span>
                          </button>
                        </div>
                      )}
                    </div>

                    {/* Source Excerpt Block */}
                    <div className="p-3.5 rounded-2xl bg-white/50 backdrop-blur-md border border-white/70 shadow-2xs">
                      <div className="flex items-center justify-between text-[11px] text-[#8C8276] mb-1.5">
                        <span className="font-bold uppercase tracking-wider flex items-center gap-1.5">
                          <FileText className="w-3.5 h-3.5 text-[#E8622C]" />
                          Source Excerpt
                        </span>
                        <span className="font-mono text-[#5C554D]">
                          {field.sourceDocument} {field.sourcePage ? `• Page ${field.sourcePage}` : ''} {field.sourceSection ? `• ${field.sourceSection}` : ''}
                        </span>
                      </div>
                      <p className="text-xs text-[#262320] font-mono italic leading-relaxed bg-white/75 backdrop-blur-xs p-2.5 rounded-xl border border-white/60 shadow-2xs">
                        {field.sourceExcerpt}
                      </p>
                    </div>

                    {/* AI Reasoning Text Block */}
                    <div className="p-3 rounded-2xl bg-white/50 backdrop-blur-md border border-white/70 flex items-start gap-2.5 shadow-2xs">
                      <Sparkles className="w-4 h-4 text-[#E8622C] shrink-0 mt-0.5" />
                      <div>
                        <span className="text-[11px] font-bold uppercase tracking-wider text-[#8C8276] block">
                          AI Multimodal Reasoning
                        </span>
                        <p className="text-xs text-[#5C554D] mt-0.5 leading-relaxed">
                          {field.aiReasoning}
                        </p>
                      </div>
                    </div>

                    {/* Sources Disagree Expandable Conflict Panel (Phase 7) */}
                    {(() => {
                      const conflict = ((product as any).conflicts || []).find(
                        (c: any) => c.field_name === field.name || c.field_name === field.id
                      );
                      const hasConflict = conflict || field.aiReasoning.includes('disagreement') || field.aiReasoning.includes('Conflict');
                      if (!hasConflict) return null;

                      return (
                        <div className="p-4 rounded-2xl bg-[#FFF9F2] border border-[#F5C29B] shadow-2xs space-y-3">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2 text-xs font-bold text-[#D45320]">
                              <AlertTriangle className="w-4 h-4 text-[#E8622C]" />
                              <span>Sources Disagree (Cross-Source Conflict Detected)</span>
                            </div>
                            <span className="text-[10px] font-mono font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-[#E8622C]/10 text-[#E8622C] border border-[#E8622C]/20">
                              Resolved Conf: {conflict?.resolved_confidence || field.confidence}%
                            </span>
                          </div>

                          <p className="text-xs text-[#5C554D] leading-relaxed">
                            {conflict?.resolution_reasoning || field.aiReasoning}
                          </p>

                          {conflict?.candidates && conflict.candidates.length > 0 && (
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 pt-1">
                              {conflict.candidates.map((cand: any, idx: number) => (
                                <div
                                  key={idx}
                                  className={`p-3 rounded-xl border text-xs space-y-1.5 ${
                                    String(cand.value) === String(conflict.resolution)
                                      ? 'bg-white border-[#E8622C] ring-1 ring-[#E8622C]/30 shadow-2xs'
                                      : 'bg-white/80 border-[#EAD5C3] text-[#5C554D]'
                                  }`}
                                >
                                  <div className="flex items-center justify-between">
                                    <span className="font-mono text-[10px] font-bold uppercase text-[#8C8276]">
                                      Source Tier {cand.trust_tier} {cand.trust_tier === 1 ? '(OEM Website)' : cand.trust_tier === 2 ? '(Spec PDF)' : '(Catalog)'}
                                    </span>
                                    {String(cand.value) === String(conflict.resolution) && (
                                      <span className="text-[10px] font-bold text-[#E8622C] flex items-center gap-1">
                                        <Check className="w-3 h-3" /> Winner
                                      </span>
                                    )}
                                  </div>
                                  <div className="font-display font-bold text-sm text-[#191715]">
                                    {String(cand.value)}
                                  </div>
                                  {cand.raw_excerpt && (
                                    <p className="text-[11px] text-[#8C8276] italic font-mono bg-[#FAF4EB] p-2 rounded-lg border border-[#EAD5C3]/50">
                                      "{cand.raw_excerpt}"
                                    </p>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })()}
                  </div>

                  {/* Right: Circular Confidence Ring for this specific field */}
                  <div className="flex flex-col items-center justify-center p-4 bg-white/60 backdrop-blur-xl rounded-2xl border border-white/70 shadow-2xs shrink-0 self-center lg:self-stretch min-w-[120px]">
                    <CircularProgress
                      value={field.confidence}
                      size={72}
                      strokeWidth={7}
                      color={field.confidence >= 85 ? 'orange' : field.confidence >= 65 ? 'charcoal' : 'amber'}
                    />
                    <span className="text-[10px] font-bold uppercase tracking-wider text-[#8C8276] mt-1.5">
                      Field Confidence
                    </span>
                  </div>
                </div>
              </div>
            );
          })}

          {/* Export Delivery CSV — shown at the bottom of the fields list after completion */}
          {(product.confidence >= 85 || product.fields.every(f => f.isApproved)) && (
            <div className="mt-6 p-6 bg-white/70 backdrop-blur-2xl rounded-3xl border border-[#1F8A53]/30 ring-1 ring-[#1F8A53]/10 shadow-[0_8px_32px_rgba(26,23,21,0.04)] flex flex-col sm:flex-row items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-2xl bg-[#EAF5EE]/90 backdrop-blur-md text-[#1F8A53] flex items-center justify-center border border-[#1F8A53]/20 shadow-xs">
                  <ShieldCheck className="w-5 h-5" />
                </div>
                <div>
                  <h4 className="font-display font-bold text-sm text-[#191715]">Ready for Export</h4>
                  <p className="text-xs text-[#5C554D] mt-0.5">
                    All {product.fields.length} fields meet the confidence threshold. Export this product record in Unihack 252-column Delivery CSV format.
                  </p>
                </div>
              </div>
              <a
                href="http://localhost:8000/api/export/csv"
                download="Unihack_Delivery_Format.csv"
                className="px-5 py-2.5 rounded-full bg-gradient-to-r from-[#1F8A53] to-[#177A48] hover:scale-[1.02] active:scale-[0.98] text-white text-xs font-bold flex items-center justify-center gap-2 shadow-md shadow-[#1F8A53]/25 border border-white/20 transition-all cursor-pointer whitespace-nowrap"
                title="Export catalog in exact Unihack 252-column Delivery CSV format"
              >
                <FileText className="w-4 h-4" />
                <span>Export Delivery CSV</span>
              </a>
            </div>
          )}
        </div>
      ) : (
        /* Source Document PDF / Datasheet Simulator View */
        <div className="bg-white/70 backdrop-blur-2xl rounded-3xl p-6 sm:p-8 border border-white/80 ring-1 ring-white/50 shadow-[0_8px_32px_rgba(26,23,21,0.04)] space-y-6">
          <div className="flex items-center justify-between pb-4 border-b border-white/60">
            <div>
              <h3 className="font-display font-bold text-lg text-[#191715]">
                Datasheet Document Inspector: {product.sourceDocument}
              </h3>
              <p className="text-xs text-[#8C8276] mt-0.5">
                AI optical bounding boxes & table extraction layer
              </p>
            </div>
            <button className="px-3.5 py-1.5 rounded-full bg-white/70 hover:bg-white/95 backdrop-blur-md text-xs font-bold text-[#191715] flex items-center gap-1.5 border border-white/70 shadow-2xs transition-colors cursor-pointer">
              <ExternalLink className="w-3.5 h-3.5" />
              <span>Open Raw PDF</span>
            </button>
          </div>

          <div className="p-8 rounded-2xl bg-white/50 backdrop-blur-md border-2 border-dashed border-white/80 flex flex-col items-center justify-center text-center space-y-4 shadow-inner">
            <div className="w-14 h-14 rounded-2xl bg-white/90 backdrop-blur-md shadow-md flex items-center justify-center text-[#E8622C] border border-white/80">
              <FileText className="w-7 h-7" />
            </div>
            <div className="max-w-md">
              <h4 className="font-display font-bold text-base text-[#191715]">
                Multimodal OCR & Vector Spatial Alignment
              </h4>
              <p className="text-xs text-[#5C554D] mt-1 leading-relaxed">
                Ledger parsed 14 tables and 6 specification columns across 8 pages of <strong>{product.sourceDocument}</strong>. All extracted entities are referenced above.
              </p>
            </div>
            <button
              onClick={() => setActiveInspectorTab('fields')}
              className="px-5 py-2.5 rounded-full bg-gradient-to-r from-[#E8622C] to-[#D45320] text-white text-xs font-bold hover:scale-[1.02] shadow-md shadow-[#E8622C]/25 border border-white/20 transition-all cursor-pointer"
            >
              Return to Extracted Attributes
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

