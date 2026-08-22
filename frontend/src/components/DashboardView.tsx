import React, { useState } from 'react';
import { 
  ArrowUpRight, 
  CheckCircle, 
  AlertTriangle, 
  Sparkles, 
  ArrowRight, 
  Clock, 
  FileText, 
  ChevronRight, 
  Check, 
  X, 
  ShieldCheck, 
  Database,
  Cpu,
  Factory,
  Headphones,
  Bot,
  Lightbulb,
  HeartPulse,
  TrendingUp,
  Eye
} from 'lucide-react';
import { ProductRecord, IngestionSource, CategoryOverview } from '../types';
import { StatusPill } from './StatusPill';
import { CatalogHealthTrendChart } from './CatalogHealthTrendChart';
import { ConfidenceHeatmap } from './ConfidenceHeatmap';

interface DashboardViewProps {
  products: ProductRecord[];
  sources: IngestionSource[];
  categories: CategoryOverview[];
  onSelectProduct: (product: ProductRecord) => void;
  onApproveProduct: (productId: string) => void;
  onOpenIngestModal: () => void;
  onNavigateToTab: (tab: any) => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  products,
  sources,
  categories,
  onSelectProduct,
  onApproveProduct,
  onOpenIngestModal,
  onNavigateToTab
}) => {
  const [activeCategoryIndex, setActiveCategoryIndex] = useState(0);

  // Compute live metrics
  const totalProducts = products.length;
  const needsReviewProducts = products.filter(p => p.status === 'needs_review' || p.status === 'flagged_conflict');
  const autoCommittedProducts = products.filter(p => p.status === 'auto_committed' || p.status === 'human_corrected');
  
  const avgConfidence = Math.round(
    products.reduce((acc, curr) => acc + curr.confidence, 0) / (totalProducts || 1)
  );

  const autoCommitRate = totalProducts > 0 
    ? Math.round((autoCommittedProducts.length / totalProducts) * 100) 
    : 0;

  const confidenceGrade = avgConfidence >= 90 ? 'A++' : avgConfidence >= 80 ? 'A' : avgConfidence >= 70 ? 'B' : 'C';

  const activeCategory = categories[activeCategoryIndex] || categories[0];

  return (
    <div className="flex flex-col gap-8 pb-16">
      {/* ========================================================
          HEADER (Exact Artistic Flair Match with Didone Serif & Italics)
          ======================================================== */}
      <header className="flex flex-col lg:flex-row justify-between items-start lg:items-end gap-6">
        <div className="flex flex-col gap-2">
          <span className="text-[10px] font-bold tracking-[0.2em] uppercase opacity-60 text-[#1A1A1A]">
            Autonomous Intelligence • Active Pipeline
          </span>
          <h1 className="text-4xl sm:text-6xl lg:text-7xl font-didone font-bold tracking-tight leading-[0.92] text-[#1A1A1A]">
            Trust Your <span className="font-didone-italic text-[#E8622C] font-normal">Catalog.</span>
          </h1>
          <p className="text-xs sm:text-sm text-[#1A1A1A]/70 font-medium max-w-xl mt-1">
            Multimodal extraction pipeline with verified provenance tracking and automated attribute confidence scoring.
          </p>
        </div>

        <div className="flex flex-wrap sm:flex-nowrap gap-4 shrink-0">
          {/* Stat Card 1: Confidence Level - Frosted Glass Card */}
          <div className="bg-white/70 backdrop-blur-xl p-5 rounded-[24px] shadow-[0_8px_32px_rgba(26,23,21,0.05)] flex items-center gap-4 w-52 border border-white/80 ring-1 ring-white/50">
            <div className="relative w-12 h-12 flex items-center justify-center shrink-0">
              <div className="absolute inset-0 rounded-full border-[5px] border-white/40"></div>
              <div className="absolute inset-0 rounded-full border-[5px] border-[#E8622C] border-t-transparent -rotate-45"></div>
              <span className="text-xs font-black text-[#1A1A1A]">{avgConfidence}%</span>
            </div>
            <div>
              <p className="text-[10px] font-bold opacity-50 uppercase tracking-wider text-[#1A1A1A]">Confidence</p>
              <p className="text-lg font-didone font-bold text-[#1A1A1A]"><span className="font-didone-italic text-[#E8622C]">{confidenceGrade}</span> Level</p>
            </div>
          </div>

          {/* Stat Card 2: Auto-Sync - Dark Frosted Glass Card */}
          <div className="bg-[#1A1A1A]/85 backdrop-blur-xl p-5 rounded-[24px] shadow-[0_8px_32px_rgba(0,0,0,0.18)] flex items-center gap-4 w-52 text-white shrink-0 border border-white/15 ring-1 ring-white/10">
            <div className="relative w-12 h-12 flex items-center justify-center shrink-0">
              <div className="absolute inset-0 rounded-full border-[5px] border-white/10"></div>
              <div className="absolute inset-0 rounded-full border-[5px] border-[#E8622C] border-t-transparent border-l-transparent rotate-[120deg]"></div>
              <span className="text-xs font-black text-white">{autoCommitRate}%</span>
            </div>
            <div>
              <p className="text-[10px] font-bold opacity-50 uppercase tracking-wider text-white">Auto-Sync</p>
              <p className="text-lg font-didone font-bold text-white"><span className="font-didone-italic text-[#E8622C]">Enabled</span></p>
            </div>
          </div>
        </div>
      </header>

      {/* ========================================================
          30-DAY CATALOG CONFIDENCE & HEALTH TREND (Recharts)
          ======================================================== */}
      <CatalogHealthTrendChart products={products} currentLiveScore={avgConfidence} />

      {/* ========================================================
          PRODUCT CATEGORY CONFIDENCE HEATMAP MATRIX
          ======================================================== */}
      <ConfidenceHeatmap
        products={products}
        categories={categories}
        onSelectProduct={onSelectProduct}
        onNavigateToTab={onNavigateToTab}
      />

      {/* ========================================================
          MAIN DASHBOARD GRID (Artistic Flair 3-Column Glass Layout)
          ======================================================== */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left 2 Columns: Needs Review Queue Table Glass Card */}
        <div className="lg:col-span-2 bg-white/70 backdrop-blur-2xl rounded-[32px] p-6 sm:p-8 shadow-[0_8px_32px_rgba(26,23,21,0.06)] flex flex-col border border-white/80 ring-1 ring-white/50">
          <div className="flex justify-between items-center mb-6">
            <div>
              <h3 className="font-didone font-bold text-2xl text-[#1A1A1A]">
                Needs Review <span className="font-didone-italic text-[#E8622C] font-normal">Queue</span>
              </h3>
              <p className="text-xs text-[#1A1A1A]/60 mt-0.5">
                {needsReviewProducts.length} items flagged for human verification & attribution
              </p>
            </div>
            <button
              onClick={() => onNavigateToTab('review_queue')}
              className="text-xs font-bold underline underline-offset-4 opacity-70 hover:opacity-100 hover:text-[#E8622C] transition-all cursor-pointer text-[#1A1A1A]"
            >
              View All Records
            </button>
          </div>

          <div className="flex-1 flex flex-col">
            {/* Table Header */}
            <div className="grid grid-cols-4 px-4 py-2 text-[10px] font-bold uppercase tracking-widest opacity-40 text-[#1A1A1A]">
              <span>Product Name</span>
              <span>Category</span>
              <span>Confidence</span>
              <span className="text-right">Priority</span>
            </div>

            {/* Table Rows */}
            <div className="flex flex-col divide-y divide-white/60">
              {products.length === 0 ? (
                <div className="py-12 text-center flex flex-col items-center justify-center">
                  <div className="w-14 h-14 rounded-2xl bg-white/80 text-[#E8622C] flex items-center justify-center mb-3 shadow-sm border border-white/80">
                    <Sparkles className="w-7 h-7" />
                  </div>
                  <h4 className="font-didone font-bold text-xl text-[#1A1A1A]">Catalog Ready for Live Data</h4>
                  <p className="text-xs text-[#1A1A1A]/60 max-w-md mt-1.5 mb-5 leading-relaxed">
                    Upload PDF datasheets, CSV product tables, or paste specification text. The Google GenAI Agent Engine will extract 252-column attributes in real time.
                  </p>
                  <button
                    onClick={onOpenIngestModal}
                    className="px-6 py-3 rounded-full bg-gradient-to-r from-[#E8622C] to-[#D45320] text-white text-xs font-bold shadow-md shadow-[#E8622C]/25 hover:scale-[1.02] transition-all cursor-pointer"
                  >
                    + Ingest First Source
                  </button>
                </div>
              ) : (
                products.slice(0, 6).map((product) => (
                  <div
                    key={product.id}
                    onClick={() => {
                      onSelectProduct(product);
                      onNavigateToTab('field_inspector');
                    }}
                    className="grid grid-cols-4 items-center p-4 hover:bg-white/60 hover:backdrop-blur-md rounded-2xl transition-all cursor-pointer group"
                  >
                    {/* Product Name */}
                    <div className="min-w-0 pr-2">
                      <span className="font-bold text-sm text-[#1A1A1A] group-hover:text-[#E8622C] transition-colors truncate block">
                        {product.name}
                      </span>
                      <span className="text-[11px] font-mono opacity-50 truncate block">
                        {product.sku}
                      </span>
                    </div>

                    {/* Category */}
                    <span className="text-sm opacity-70 text-[#1A1A1A] truncate pr-2">
                      {product.category}
                    </span>

                    {/* Confidence Bar & Number */}
                    <div className="flex items-center gap-2">
                      <div className="w-16 sm:w-20 h-1.5 bg-white/60 rounded-full overflow-hidden shrink-0 border border-white/40">
                        <div
                          className={`h-full ${
                            product.confidence >= 85 ? 'bg-[#E8622C]' : 'bg-[#1A1A1A]'
                          }`}
                          style={{ width: `${product.confidence}%` }}
                        />
                      </div>
                      <span className="text-xs font-bold text-[#1A1A1A]">{product.confidence}%</span>
                    </div>

                    {/* Priority / Action */}
                    <div className="flex justify-end items-center gap-2">
                      <StatusPill
                        type="confidence"
                        confidenceScore={product.confidence}
                        label={product.confidence >= 85 ? 'High' : product.confidence >= 65 ? 'Med' : 'Low'}
                        size="sm"
                      />
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Right 1 Column: Category Overview & Recent Ingestions */}
        <div className="flex flex-col gap-6">
          {/* Card 1: Orange Category Overview Frosted Glass Banner */}
          <div className="bg-gradient-to-br from-[#E8622C]/90 to-[#D45320]/95 backdrop-blur-2xl p-6 sm:p-8 rounded-[32px] text-white shadow-[0_12px_36px_rgba(232,98,44,0.28)] flex flex-col gap-4 relative overflow-hidden border border-white/30 ring-1 ring-white/20">
            <div className="absolute -right-6 -top-6 w-32 h-32 bg-white/15 rounded-full blur-xs pointer-events-none" />
            
            <div className="flex justify-between items-start">
              <span className="text-[10px] font-bold tracking-[0.2em] uppercase opacity-80">
                Category Overview
              </span>
              <div className="flex gap-1 bg-black/15 backdrop-blur-sm rounded-full p-1 border border-white/10">
                {categories.slice(0, 3).map((c, i) => (
                  <button
                    key={c.id}
                    onClick={() => setActiveCategoryIndex(i)}
                    className={`w-2 h-2 rounded-full transition-all ${
                      activeCategoryIndex === i ? 'bg-white scale-125' : 'bg-white/40'
                    }`}
                  />
                ))}
              </div>
            </div>

            <div>
              <h4 className="text-2xl font-didone font-bold leading-none tracking-tight">
                {activeCategory?.name || 'Industrial & Sensorics'}
              </h4>
              <p className="text-xs text-white/90 mt-1 font-didone-italic">
                {activeCategory?.totalRecords.toLocaleString()} Verified SKU Records
              </p>
            </div>

            <div className="space-y-3 pt-2">
              <div className="flex justify-between text-xs font-bold">
                <span className="opacity-85">Extraction Confidence</span>
                <span>{activeCategory?.avgConfidence}%</span>
              </div>
              <div className="w-full h-2 bg-white/25 backdrop-blur-xs rounded-full overflow-hidden">
                <div 
                  className="h-full bg-white rounded-full transition-all duration-300"
                  style={{ width: `${activeCategory?.avgConfidence}%` }}
                />
              </div>

              <div className="flex justify-between items-center pt-2 text-xs border-t border-white/20">
                <span className="opacity-85">Needs Review</span>
                <span className="font-bold px-2 py-0.5 rounded-full bg-white/25 backdrop-blur-xs">
                  {activeCategory?.needsReviewCount} Items
                </span>
              </div>
            </div>
          </div>

          {/* Card 2: Recent Ingestions Frosted Glass Card */}
          <div className="bg-white/70 backdrop-blur-2xl p-6 sm:p-8 rounded-[32px] shadow-[0_8px_32px_rgba(26,23,21,0.06)] flex-1 flex flex-col justify-between border border-white/80 ring-1 ring-white/50">
            <div>
              <div className="flex justify-between items-center mb-6">
                <h4 className="font-black text-lg text-[#1A1A1A]">Recent Ingestions</h4>
                <button
                  onClick={() => onNavigateToTab('sources')}
                  className="text-xs font-bold opacity-50 hover:opacity-100 transition-opacity cursor-pointer"
                >
                  All Feeds
                </button>
              </div>

              <div className="flex flex-col gap-4">
                {sources.slice(0, 3).map((source) => (
                  <div key={source.id} className="flex items-center gap-3">
                    <div className="w-2 h-2 rounded-full bg-[#E8622C] shrink-0" />
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-bold text-[#1A1A1A] truncate">
                        {source.name}
                      </p>
                      <p className="text-[10px] opacity-50 uppercase tracking-wider text-[#1A1A1A]">
                        {source.recordsCount} items • {source.timestamp}
                      </p>
                    </div>
                    <span className="text-[10px] font-bold px-2.5 py-0.5 rounded-full bg-white/60 backdrop-blur-md text-[#1A1A1A] border border-white/70 shadow-2xs">
                      {source.avgConfidence}%
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <button
              onClick={onOpenIngestModal}
              className="mt-6 w-full py-3.5 bg-white/50 hover:bg-white/80 backdrop-blur-md border border-white/80 rounded-2xl text-xs font-black uppercase tracking-widest transition-all text-[#1A1A1A] cursor-pointer shadow-xs hover:shadow-md"
            >
              + Ingest Pipeline
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

