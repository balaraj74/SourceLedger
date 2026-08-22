import React, { useState, useMemo } from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine
} from 'recharts';
import { 
  TrendingUp, 
  TrendingDown,
  ShieldCheck, 
  Activity, 
  Calendar, 
  Sparkles, 
  CheckCircle2, 
  ArrowUpRight,
  ArrowDownRight,
  AlertTriangle,
  Award,
  Layers,
  Info,
  Zap,
  Filter,
  FileText
} from 'lucide-react';
import { ProductRecord } from '../types';

// Keep type for chart compatibility
export interface DailyTrendPoint {
  date: string;
  day: number;
  confidence: number;
  confidenceDelta: number;
  autoCommitRate: number;
  resolvedConflicts: number;
  healthIndex: number;
  totalSkus: number;
  annotation?: {
    type: 'spike' | 'dip' | 'milestone' | 'steady';
    title: string;
    cause: string;
    impact: string;
    badge: string;
    sourceType?: string;
  };
}

interface CatalogHealthTrendChartProps {
  products: ProductRecord[];
  currentLiveScore?: number;
}

export const CatalogHealthTrendChart: React.FC<CatalogHealthTrendChartProps> = ({
  products,
  currentLiveScore
}) => {
  const [timeframe, setTimeframe] = useState<'1' | '7' | '14' | '30'>('30');
  const [showAutoCommit, setShowAutoCommit] = useState(true);
  const [showHealthIndex, setShowHealthIndex] = useState(true);
  const [eventFilter, setEventFilter] = useState<'all' | 'spikes' | 'dips' | 'milestones'>('all');
  const [selectedPoint, setSelectedPoint] = useState<DailyTrendPoint | null>(null);

  // ── Compute REAL trend data from actual products in Database ──────────────────
  const rawData = useMemo<DailyTrendPoint[]>(() => {
    const safeProducts = products || [];
    if (safeProducts.length === 0) return [];

    const now = new Date();

    if (timeframe === '1') {
      // ── 1 DAY VIEW: Hourly breakdown (Past 24 Hours) ──────────────────
      const points: DailyTrendPoint[] = [];

      // Generate 12 two-hour interval buckets for today (00:00, 02:00, ... 22:00)
      for (let h = 0; h < 24; h += 2) {
        const hourLabel = `${h.toString().padStart(2, '0')}:00`;

        const prodsUpToHour = safeProducts.filter(p => {
          if (!p.createdAt) return true;
          try {
            const d = new Date(p.createdAt);
            return d.getHours() <= h || d.getDate() < now.getDate();
          } catch {
            return true;
          }
        });

        const activeProds = prodsUpToHour.length > 0 ? prodsUpToHour : safeProducts;
        const totalCount = activeProds.length;
        const sumConf = activeProds.reduce((acc, p) => acc + (p.confidence || 0), 0);
        const avgConf = +(sumConf / (totalCount || 1)).toFixed(1);

        const autoCount = activeProds.filter(
          p => p.status === 'auto_committed' || p.status === 'human_corrected'
        ).length;
        const reviewedCount = activeProds.filter(p => p.status === 'human_corrected').length;
        const autoRate = +((autoCount / (totalCount || 1)) * 100).toFixed(1);
        const healthIdx = +(avgConf * 0.7 + autoRate * 0.3).toFixed(1);

        const prevPoint = points[points.length - 1];
        const delta = prevPoint ? +(avgConf - prevPoint.confidence).toFixed(1) : 0;

        const point: DailyTrendPoint = {
          date: hourLabel,
          day: Math.floor(h / 2) + 1,
          confidence: isNaN(avgConf) ? 0 : avgConf,
          confidenceDelta: isNaN(delta) ? 0 : delta,
          autoCommitRate: isNaN(autoRate) ? 0 : autoRate,
          resolvedConflicts: reviewedCount,
          healthIndex: isNaN(healthIdx) ? 0 : healthIdx,
          totalSkus: totalCount,
        };

        if (h === 0 && activeProds.length > 0) {
          const firstP = activeProds[0];
          point.annotation = {
            type: 'milestone',
            title: '1-Day Window Baseline',
            cause: `"${(firstP?.name || 'Product').slice(0, 40)}" extracted with ${firstP?.fieldsCount || 0} fields.`,
            impact: `Initial 24h baseline confidence: ${avgConf}%`,
            badge: '24h Monitor',
            sourceType: firstP?.category,
          };
        } else if (avgConf >= 90 && (!prevPoint || prevPoint.confidence < 90)) {
          point.annotation = {
            type: 'milestone',
            title: '90% Quality Level',
            cause: `Hourly quality score achieved ${avgConf}% across active pipeline.`,
            impact: `${autoCount} SKUs auto-committed cleanly.`,
            badge: 'Quality Milestone',
          };
        }

        points.push(point);
      }

      return points;
    } else {
      // ── MULTI-DAY VIEWS (7, 14, 30 Days): Real Date Aggregation ──────
      const daysCount = parseInt(timeframe, 10);
      const points: DailyTrendPoint[] = [];

      for (let i = daysCount - 1; i >= 0; i--) {
        const targetDate = new Date(now);
        targetDate.setDate(now.getDate() - i);
        const dateStr = targetDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

        const prodsOnDate = safeProducts.filter(p => {
          if (!p.createdAt) return true;
          try {
            const d = new Date(p.createdAt);
            return d <= targetDate || (d.getDate() === targetDate.getDate() && d.getMonth() === targetDate.getMonth());
          } catch {
            return true;
          }
        });

        const activeProds = prodsOnDate.length > 0 ? prodsOnDate : safeProducts;
        const totalCount = activeProds.length;
        const sumConf = activeProds.reduce((acc, p) => acc + (p.confidence || 0), 0);
        const avgConf = +(sumConf / (totalCount || 1)).toFixed(1);

        const autoCount = activeProds.filter(
          p => p.status === 'auto_committed' || p.status === 'human_corrected'
        ).length;
        const reviewedCount = activeProds.filter(p => p.status === 'human_corrected').length;
        const autoRate = +((autoCount / (totalCount || 1)) * 100).toFixed(1);
        const healthIdx = +(avgConf * 0.7 + autoRate * 0.3).toFixed(1);

        const prevPoint = points[points.length - 1];
        const delta = prevPoint ? +(avgConf - prevPoint.confidence).toFixed(1) : 0;

        const point: DailyTrendPoint = {
          date: dateStr,
          day: daysCount - i,
          confidence: isNaN(avgConf) ? 0 : avgConf,
          confidenceDelta: isNaN(delta) ? 0 : delta,
          autoCommitRate: isNaN(autoRate) ? 0 : autoRate,
          resolvedConflicts: reviewedCount,
          healthIndex: isNaN(healthIdx) ? 0 : healthIdx,
          totalSkus: totalCount,
        };

        if (i === daysCount - 1 && activeProds.length > 0) {
          const firstP = activeProds[0];
          point.annotation = {
            type: 'milestone',
            title: 'First Product Ingested',
            cause: `"${(firstP?.name || 'Product').slice(0, 40)}" extracted with ${firstP?.fieldsCount || 0} fields.`,
            impact: `Baseline confidence: ${avgConf}%`,
            badge: 'Pipeline Start',
            sourceType: firstP?.category,
          };
        } else if (i === 0 && avgConf >= 85) {
          point.annotation = {
            type: 'milestone',
            title: 'Current Quality Goal',
            cause: `Running catalog average reached ${avgConf}% across ${totalCount} SKUs.`,
            impact: `${autoCount} SKUs auto-committed.`,
            badge: 'Quality Milestone',
          };
        }

        points.push(point);
      }

      return points;
    }
  }, [products, timeframe]);

  const filteredData = rawData;

  const startPoint = filteredData[0];
  const endPoint = filteredData[filteredData.length - 1];
  const deltaConfidence = endPoint && startPoint ? +(endPoint.confidence - startPoint.confidence).toFixed(1) : 0;

  // Compute real stats safely
  const safeProds = products || [];
  const totalProducts = safeProds.length;
  const autoCommitted = safeProds.filter(p => p?.status === 'auto_committed' || p?.status === 'human_corrected').length;
  const autoCommitRate = totalProducts > 0 ? +((autoCommitted / totalProducts) * 100).toFixed(1) : 0;
  const avgConfidence = totalProducts > 0 ? Math.round(safeProds.reduce((s, p) => s + (p?.confidence || 0), 0) / totalProducts) : 0;
  const reviewedFields = safeProds.reduce((s, p) => s + (p?.fieldsReviewedCount || 0), 0);
  const healthScore = totalProducts > 0 ? +(avgConfidence * 0.7 + autoCommitRate * 0.3).toFixed(1) : 0;

  // Annotated events in current filtered timeframe
  const eventsInView = useMemo(() => {
    return filteredData.filter(d => {
      if (!d.annotation) return false;
      if (eventFilter === 'spikes') return d.annotation.type === 'spike';
      if (eventFilter === 'dips') return d.annotation.type === 'dip';
      if (eventFilter === 'milestones') return d.annotation.type === 'milestone';
      return true;
    });
  }, [filteredData, eventFilter]);

  // Custom Dot for Primary Confidence Line
  const renderCustomDot = (props: any) => {
    const { cx, cy, payload } = props;
    if (cx === undefined || cy === undefined || isNaN(cx) || isNaN(cy) || !payload) return null;
    const point: DailyTrendPoint = payload;
    const isSelected = selectedPoint?.day === point.day;

    if (point.annotation?.type === 'spike') {
      return (
        <g key={`dot-${point.day}`} className="cursor-pointer">
          <circle cx={cx} cy={cy} r={isSelected ? 9 : 7} fill="#E8622C" fillOpacity={0.25} className="animate-pulse" />
          <circle cx={cx} cy={cy} r={isSelected ? 5 : 4} fill="#E8622C" stroke="#FFFFFF" strokeWidth={2} />
          {isSelected && (
            <circle cx={cx} cy={cy} r={2} fill="#FFFFFF" />
          )}
        </g>
      );
    }

    if (point.annotation?.type === 'dip') {
      return (
        <g key={`dot-${point.day}`} className="cursor-pointer">
          <circle cx={cx} cy={cy} r={isSelected ? 9 : 7} fill="#D45320" fillOpacity={0.25} />
          <circle cx={cx} cy={cy} r={isSelected ? 5 : 4} fill="#D45320" stroke="#FFFFFF" strokeWidth={2} />
        </g>
      );
    }

    if (point.annotation?.type === 'milestone') {
      return (
        <g key={`dot-${point.day}`} className="cursor-pointer">
          <circle cx={cx} cy={cy} r={isSelected ? 8 : 6} fill="#F2A900" fillOpacity={0.3} />
          <circle cx={cx} cy={cy} r={isSelected ? 4.5 : 3.5} fill="#D97706" stroke="#FFFFFF" strokeWidth={2} />
        </g>
      );
    }

    return (
      <circle
        key={`dot-${point.day}`}
        cx={cx}
        cy={cy}
        r={isSelected ? 5 : 2.5}
        fill="#E8622C"
        stroke="#FFFFFF"
        strokeWidth={isSelected ? 2 : 1.5}
      />
    );
  };

  // Enhanced Dynamic Glassmorphic Tooltip
  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length && payload[0]?.payload) {
      const data: DailyTrendPoint = payload[0].payload;
      const annotation = data.annotation;
      const hasDelta = data.confidenceDelta !== 0;
      const isPositive = data.confidenceDelta > 0;

      return (
        <div className="bg-white/95 backdrop-blur-2xl p-4 sm:p-5 rounded-3xl border border-white shadow-[0_16px_40px_rgba(26,23,21,0.16)] ring-1 ring-white/60 text-xs min-w-[280px] max-w-[340px] space-y-3 animate-in fade-in zoom-in-95 duration-150 z-50">
          {/* Header with Date & Day-over-Day Delta */}
          <div className="flex items-center justify-between border-b border-[#FAF4EB] pb-2.5">
            <div className="flex items-center gap-2">
              <span className="w-6 h-6 rounded-xl bg-[#FAF4EB] flex items-center justify-center text-[#E8622C] font-bold">
                <Calendar className="w-3.5 h-3.5" />
              </span>
              <div>
                <span className="font-bold text-sm text-[#191715] font-didone">
                  {data.date}
                </span>
                <span className="text-[10px] text-[#8C8276] block font-mono">Day {data.day} of cycle</span>
              </div>
            </div>

            {hasDelta && (
              <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-extrabold ${
                isPositive 
                  ? 'bg-[#E8622C]/10 text-[#E8622C] border border-[#E8622C]/20'
                  : 'bg-[#D45320]/10 text-[#D45320] border border-[#D45320]/20'
              }`}>
                {isPositive ? (
                  <TrendingUp className="w-3.5 h-3.5 stroke-[2.5]" />
                ) : (
                  <TrendingDown className="w-3.5 h-3.5 stroke-[2.5]" />
                )}
                {isPositive ? `+${data.confidenceDelta}%` : `${data.confidenceDelta}%`}
              </span>
            )}
          </div>

          {/* Primary Metrics Group */}
          <div className="grid grid-cols-2 gap-2 bg-[#FCFAF7] p-2.5 rounded-2xl border border-[#FAF4EB]">
            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-[#8C8276] flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-[#E8622C]" />
                Confidence
              </span>
              <span className="font-didone text-lg font-bold text-[#E8622C] block mt-0.5">
                {data.confidence}%
              </span>
            </div>

            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-[#8C8276] flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-[#1F8A53]" />
                Health Index
              </span>
              <span className="font-didone text-lg font-bold text-[#1F8A53] block mt-0.5">
                {data.healthIndex}<span className="text-xs font-normal text-[#8C8276]">/100</span>
              </span>
            </div>

            {showAutoCommit && (
              <div className="col-span-2 pt-1 border-t border-[#FAF4EB] flex items-center justify-between text-[11px]">
                <span className="text-[#5C554D] font-medium">Auto-Commit Rate:</span>
                <span className="font-bold text-[#191715]">{data.autoCommitRate}%</span>
              </div>
            )}
          </div>

          {/* DYNAMIC EVENT ANNOTATION CALLOUT (Spike, Dip, Milestone) */}
          {annotation ? (
            <div className={`p-3 rounded-2xl border transition-all ${
              annotation.type === 'spike'
                ? 'bg-gradient-to-br from-[#FFF5F0] to-[#FAF4EB] border-[#E8622C]/30 text-[#191715]'
                : annotation.type === 'dip'
                ? 'bg-gradient-to-br from-[#FFF0ED] to-[#FAF4EB] border-[#D45320]/30 text-[#191715]'
                : 'bg-gradient-to-br from-[#FFFDF0] to-[#FAF4EB] border-[#D97706]/30 text-[#191715]'
            }`}>
              {/* Event Type Header */}
              <div className="flex items-center justify-between mb-1.5">
                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-extrabold uppercase tracking-wider ${
                  annotation.type === 'spike'
                    ? 'bg-[#E8622C] text-white'
                    : annotation.type === 'dip'
                    ? 'bg-[#D45320] text-white'
                    : 'bg-[#D97706] text-white'
                }`}>
                  {annotation.type === 'spike' && <Zap className="w-3 h-3" />}
                  {annotation.type === 'dip' && <AlertTriangle className="w-3 h-3" />}
                  {annotation.type === 'milestone' && <Award className="w-3 h-3" />}
                  {annotation.badge}
                </span>

                {annotation.sourceType && (
                  <span className="text-[10px] font-mono text-[#8C8276] font-semibold">
                    {annotation.sourceType}
                  </span>
                )}
              </div>

              {/* Event Title */}
              <h5 className="font-didone font-bold text-xs text-[#191715] leading-snug">
                {annotation.title}
              </h5>

              {/* Root Cause Explanation */}
              <div className="mt-1.5 pt-1.5 border-t border-black/5 space-y-1 text-[11px] leading-relaxed">
                <p className="text-[#5C554D]">
                  <strong className="text-[#191715] font-semibold">Root Cause: </strong>
                  {annotation.cause}
                </p>
                <p className="text-[#5C554D]">
                  <strong className="text-[#191715] font-semibold">Impact: </strong>
                  {annotation.impact}
                </p>
              </div>
            </div>
          ) : (
            <div className="px-2.5 py-1.5 rounded-xl bg-[#FAF4EB]/60 text-[11px] text-[#8C8276] flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <Info className="w-3.5 h-3.5 text-[#8C8276]" />
                Continuous Ingestion Active
              </span>
              <span className="font-bold text-[#191715]">+{data.resolvedConflicts} resolved</span>
            </div>
          )}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="bg-white/70 backdrop-blur-2xl rounded-[32px] p-6 sm:p-8 shadow-[0_8px_32px_rgba(26,23,21,0.06)] border border-white/80 ring-1 ring-white/50 flex flex-col gap-6">
      {/* Header & Controls Toolbar */}
      <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4 pb-2">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/60 backdrop-blur-md text-[#E8622C] text-xs font-bold uppercase tracking-wider mb-2 border border-white/70 shadow-2xs">
            <Activity className="w-3.5 h-3.5" />
            <span>Telemetry & Quality Trajectory</span>
          </div>
          <h3 className="font-didone font-bold text-2xl sm:text-3xl text-[#1A1A1A] tracking-tight flex items-center gap-2">
            <span>{timeframe === '1' ? '24-Hour' : `${timeframe}-Day`} Catalog Confidence & <span className="font-didone-italic text-[#E8622C] font-normal">Health Trajectory</span></span>
          </h3>
          <p className="text-xs text-[#1A1A1A]/60 mt-0.5">
            Hover over any data point to inspect root-cause explanations for significant quality surges, ingestion dips, and model milestones.
          </p>
        </div>

        {/* Action / Timeframe Toolbar */}
        <div className="flex flex-wrap items-center gap-3 w-full lg:w-auto justify-between lg:justify-end">
          {/* Event Filter Pills */}
          <div className="flex items-center gap-1 bg-white/60 backdrop-blur-md p-1 rounded-2xl border border-white/70 shadow-2xs text-xs">
            <span className="text-[10px] font-bold text-[#8C8276] uppercase tracking-wider px-2 hidden sm:inline">Events:</span>
            <button
              onClick={() => setEventFilter('all')}
              className={`px-2.5 py-1 rounded-xl font-bold transition-all cursor-pointer ${
                eventFilter === 'all' ? 'bg-[#191715] text-white shadow-2xs' : 'text-[#5C554D] hover:bg-white/60'
              }`}
            >
              All
            </button>
            <button
              onClick={() => setEventFilter('spikes')}
              className={`px-2.5 py-1 rounded-xl font-bold transition-all cursor-pointer flex items-center gap-1 ${
                eventFilter === 'spikes' ? 'bg-[#E8622C] text-white shadow-2xs' : 'text-[#E8622C] hover:bg-white/60'
              }`}
            >
              <Zap className="w-3 h-3" />
              Spikes
            </button>
            <button
              onClick={() => setEventFilter('dips')}
              className={`px-2.5 py-1 rounded-xl font-bold transition-all cursor-pointer flex items-center gap-1 ${
                eventFilter === 'dips' ? 'bg-[#D45320] text-white shadow-2xs' : 'text-[#D45320] hover:bg-white/60'
              }`}
            >
              <AlertTriangle className="w-3 h-3" />
              Dips
            </button>
            <button
              onClick={() => setEventFilter('milestones')}
              className={`px-2.5 py-1 rounded-xl font-bold transition-all cursor-pointer flex items-center gap-1 ${
                eventFilter === 'milestones' ? 'bg-[#D97706] text-white shadow-2xs' : 'text-[#D97706] hover:bg-white/60'
              }`}
            >
              <Award className="w-3 h-3" />
              Milestones
            </button>
          </div>

          {/* Timeframe Selector */}
          <div className="flex items-center gap-1 bg-white/60 backdrop-blur-md p-1 rounded-2xl border border-white/70 shadow-2xs">
            {(['1', '7', '14', '30'] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTimeframe(t)}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                  timeframe === t
                    ? 'bg-[#E8622C] text-white shadow-xs'
                    : 'text-[#5C554D] hover:bg-white/60'
                }`}
              >
                {t === '1' ? '1 Day' : `${t} Days`}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Summary Improvement Stat Badges — ALL COMPUTED FROM REAL DATA */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5">
        <div className="p-3.5 rounded-2xl bg-white/60 backdrop-blur-md border border-white/70 shadow-2xs flex flex-col justify-between">
          <span className="text-[10px] font-bold uppercase tracking-wider text-[#8C8276] block">
            Avg Confidence
          </span>
          <div className="flex items-baseline gap-1.5 mt-1">
            <span className="text-xl sm:text-2xl font-didone font-bold text-[#E8622C]">
              {avgConfidence}%
            </span>
            {totalProducts > 0 && <ArrowUpRight className="w-4 h-4 text-[#E8622C] stroke-[2.5]" />}
          </div>
          <span className="text-[11px] text-[#5C554D] mt-0.5">
            {totalProducts} product{totalProducts !== 1 ? 's' : ''} ingested
          </span>
        </div>

        <div className="p-3.5 rounded-2xl bg-white/60 backdrop-blur-md border border-white/70 shadow-2xs flex flex-col justify-between">
          <span className="text-[10px] font-bold uppercase tracking-wider text-[#8C8276] block">
            Catalog Health Score
          </span>
          <div className="flex items-baseline gap-1.5 mt-1">
            <span className="text-xl sm:text-2xl font-black text-[#1F8A53]">
              {healthScore}
            </span>
            <span className="text-xs font-bold text-[#8C8276]">/ 100</span>
          </div>
          <span className="text-[11px] text-[#1F8A53] font-semibold mt-0.5 flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3" /> {healthScore >= 85 ? 'Optimal Grade' : healthScore >= 65 ? 'Good' : totalProducts === 0 ? 'No Data' : 'Needs Improvement'}
          </span>
        </div>

        <div className="p-3.5 rounded-2xl bg-white/60 backdrop-blur-md border border-white/70 shadow-2xs flex flex-col justify-between">
          <span className="text-[10px] font-bold uppercase tracking-wider text-[#8C8276] block">
            Autonomous Commit Rate
          </span>
          <div className="flex items-baseline gap-1.5 mt-1">
            <span className="text-xl sm:text-2xl font-black text-[#191715]">
              {autoCommitRate}%
            </span>
          </div>
          <span className="text-[11px] text-[#5C554D] mt-0.5">
            {autoCommitted}/{totalProducts} auto-committed
          </span>
        </div>

        <div className="p-3.5 rounded-2xl bg-white/60 backdrop-blur-md border border-white/70 shadow-2xs flex flex-col justify-between">
          <span className="text-[10px] font-bold uppercase tracking-wider text-[#8C8276] block">
            Fields Reviewed
          </span>
          <div className="flex items-baseline gap-1.5 mt-1">
            <span className="text-xl sm:text-2xl font-black text-[#191715]">
              {reviewedFields.toLocaleString()}
            </span>
            <Sparkles className="w-3.5 h-3.5 text-[#E8622C]" />
          </div>
          <span className="text-[11px] text-[#5C554D] mt-0.5">
            {totalProducts > 0 ? 'With provenance tracking' : 'No data yet'}
          </span>
        </div>
      </div>

      {/* Recharts Line Graph Canvas */}
      <div className="w-full h-72 sm:h-84 pt-2">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={filteredData}
            margin={{ top: 12, right: 12, left: -16, bottom: 0 }}
            onClick={(e: any) => {
              if (e && e.activePayload && e.activePayload.length) {
                setSelectedPoint(e.activePayload[0].payload);
              }
            }}
          >
            <defs>
              {/* Burnt Orange Gradient Fill for Confidence Area */}
              <linearGradient id="confidenceGlow" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#E8622C" stopOpacity={0.28} />
                <stop offset="95%" stopColor="#E8622C" stopOpacity={0.0} />
              </linearGradient>

              {/* Health Green Gradient Fill */}
              <linearGradient id="healthGlow" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#1F8A53" stopOpacity={0.15} />
                <stop offset="95%" stopColor="#1F8A53" stopOpacity={0.0} />
              </linearGradient>
            </defs>

            <CartesianGrid
              strokeDasharray="4 6"
              stroke="#DFCDBC"
              strokeOpacity={0.45}
              vertical={false}
            />

            <XAxis
              dataKey="date"
              axisLine={false}
              tickLine={false}
              tick={{ fill: '#8C8276', fontSize: 11, fontWeight: 600 }}
              dy={8}
            />

            <YAxis
              domain={[40, 100]}
              axisLine={false}
              tickLine={false}
              tick={{ fill: '#8C8276', fontSize: 11, fontWeight: 600 }}
              tickFormatter={(val) => `${val}%`}
              dx={-4}
            />

            <Tooltip content={<CustomTooltip />} />

            {/* Target 85% Auto-Commit Threshold Line */}
            <ReferenceLine
              y={85}
              stroke="#E8622C"
              strokeDasharray="3 3"
              strokeOpacity={0.4}
              label={{
                value: 'Target Quality Goal (85%)',
                position: 'insideTopRight',
                fill: '#E8622C',
                fontSize: 10,
                fontWeight: 700
              }}
            />

            {/* Confidence Area Gradient */}
            <Area
              type="monotone"
              dataKey="confidence"
              stroke="none"
              fill="url(#confidenceGlow)"
            />

            {/* Primary Line: Confidence Score with Custom Annotated Dots */}
            <Line
              type="monotone"
              dataKey="confidence"
              name="Confidence Score"
              stroke="#E8622C"
              strokeWidth={3.5}
              dot={renderCustomDot}
              activeDot={{ r: 7, fill: '#E8622C', stroke: '#FFFFFF', strokeWidth: 3 }}
            />

            {/* Secondary Line: Auto-Commit Rate */}
            {showAutoCommit && (
              <Line
                type="monotone"
                dataKey="autoCommitRate"
                name="Auto-Commit Rate"
                stroke="#191715"
                strokeWidth={2.2}
                strokeDasharray="4 4"
                dot={{ r: 2.5, fill: '#191715', stroke: '#FFFFFF', strokeWidth: 1.5 }}
                activeDot={{ r: 5, fill: '#191715', stroke: '#FFFFFF', strokeWidth: 2 }}
              />
            )}

            {/* Tertiary Line: Catalog Health Index */}
            {showHealthIndex && (
              <Line
                type="monotone"
                dataKey="healthIndex"
                name="Health Index"
                stroke="#1F8A53"
                strokeWidth={2.5}
                dot={{ r: 2.5, fill: '#1F8A53', stroke: '#FFFFFF', strokeWidth: 1.5 }}
                activeDot={{ r: 5, fill: '#1F8A53', stroke: '#FFFFFF', strokeWidth: 2 }}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Interactive Key Event Annotation Pills Carousel */}
      <div className="space-y-2.5 pt-1 border-t border-white/60">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-bold uppercase tracking-wider text-[#8C8276] flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-[#E8622C]" />
            Pipeline Root-Cause Event Ledger ({eventsInView.length} Significant Events)
          </span>
          <span className="text-[10px] text-[#8C8276]">Click an event to inspect details</span>
        </div>

        <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-none">
          {eventsInView.map((evt) => {
            const isSelected = selectedPoint?.day === evt.day;
            const isSpike = evt.annotation?.type === 'spike';
            const isDip = evt.annotation?.type === 'dip';

            return (
              <button
                key={evt.day}
                onClick={() => setSelectedPoint(evt)}
                className={`shrink-0 text-left p-2.5 rounded-2xl border transition-all cursor-pointer flex items-center gap-2.5 ${
                  isSelected
                    ? 'bg-white shadow-[0_4px_16px_rgba(26,23,21,0.08)] border-[#E8622C] ring-2 ring-[#E8622C]/20'
                    : 'bg-white/60 hover:bg-white/90 border-white/70 shadow-2xs'
                }`}
              >
                <div className={`w-7 h-7 rounded-xl flex items-center justify-center shrink-0 ${
                  isSpike 
                    ? 'bg-[#E8622C]/10 text-[#E8622C]' 
                    : isDip 
                    ? 'bg-[#D45320]/10 text-[#D45320]' 
                    : 'bg-[#D97706]/10 text-[#D97706]'
                }`}>
                  {isSpike && <TrendingUp className="w-4 h-4" />}
                  {isDip && <TrendingDown className="w-4 h-4" />}
                  {!isSpike && !isDip && <Award className="w-4 h-4" />}
                </div>

                <div className="pr-1">
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono text-[10px] text-[#8C8276] font-bold">{evt.date}</span>
                    <span className={`text-[10px] font-extrabold ${
                      isSpike ? 'text-[#E8622C]' : isDip ? 'text-[#D45320]' : 'text-[#D97706]'
                    }`}>
                      {evt.confidenceDelta > 0 ? `+${evt.confidenceDelta}%` : `${evt.confidenceDelta}%`}
                    </span>
                  </div>
                  <p className="text-xs font-bold text-[#191715] truncate max-w-[140px] font-didone">
                    {evt.annotation?.title}
                  </p>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Selected Point Detailed Root Cause Banner (Pinned when clicked) */}
      {selectedPoint?.annotation && (
        <div className="p-4 sm:p-5 rounded-2xl bg-gradient-to-r from-white via-white/95 to-[#FAF4EB] border border-[#E8622C]/30 shadow-[0_8px_24px_rgba(232,98,44,0.08)] animate-in fade-in slide-in-from-top-2 duration-150">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2.5 border-b border-black/5">
            <div className="flex items-center gap-2">
              <span className={`px-2.5 py-0.5 rounded-full text-xs font-extrabold flex items-center gap-1 text-white ${
                selectedPoint.annotation.type === 'spike'
                  ? 'bg-[#E8622C]'
                  : selectedPoint.annotation.type === 'dip'
                  ? 'bg-[#D45320]'
                  : 'bg-[#D97706]'
              }`}>
                {selectedPoint.annotation.type === 'spike' && <Zap className="w-3.5 h-3.5" />}
                {selectedPoint.annotation.type === 'dip' && <AlertTriangle className="w-3.5 h-3.5" />}
                {selectedPoint.annotation.type === 'milestone' && <Award className="w-3.5 h-3.5" />}
                {selectedPoint.annotation.badge}
              </span>
              <h4 className="font-didone font-bold text-base text-[#191715]">
                {selectedPoint.annotation.title}
              </h4>
            </div>

            <div className="flex items-center gap-2 text-xs font-mono text-[#8C8276]">
              <span>{selectedPoint.date} (Day {selectedPoint.day})</span>
              <span>•</span>
              <span className="font-bold text-[#E8622C]">{selectedPoint.confidence}% Confidence</span>
              <button
                onClick={() => setSelectedPoint(null)}
                className="ml-2 text-[10px] text-[#8C8276] hover:text-[#191715] underline cursor-pointer"
              >
                Dismiss
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-3 text-xs">
            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-[#8C8276] block">
                Root Cause Analysis
              </span>
              <p className="text-[#5C554D] mt-0.5 leading-relaxed">
                {selectedPoint.annotation.cause}
              </p>
            </div>

            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-[#8C8276] block">
                Catalog & Quality Impact
              </span>
              <p className="text-[#5C554D] mt-0.5 leading-relaxed">
                {selectedPoint.annotation.impact}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Chart Footer Legend & Health Annotations */}
      <div className="pt-3 border-t border-white/60 flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex flex-wrap items-center gap-5">
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-[#E8622C] shadow-2xs" />
            <span className="font-bold text-[#191715]">Confidence Score (Avg %)</span>
          </div>

          {showAutoCommit && (
            <div className="flex items-center gap-2">
              <span className="w-3 h-1 bg-[#191715] rounded-full" />
              <span className="font-semibold text-[#5C554D]">Auto-Commit Rate</span>
            </div>
          )}

          {showHealthIndex && (
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-[#1F8A53] shadow-2xs" />
              <span className="font-semibold text-[#5C554D]">Catalog Health Index</span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 text-[#8C8276] font-medium">
          <ShieldCheck className="w-4 h-4 text-[#1F8A53]" />
          <span>Real-time calibration active across all ingestion pipelines</span>
        </div>
      </div>
    </div>
  );
};
