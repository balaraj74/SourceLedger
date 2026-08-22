import React, { useEffect, useState } from 'react';
import { 
  ShieldCheck, 
  AlertTriangle, 
  FileText, 
  TrendingUp, 
  Layers, 
  Clock, 
  CheckCircle2, 
  ArrowRight,
  RefreshCw
} from 'lucide-react';
import { getQualityDashboard, QualityDashboardData } from '../lib/api';

interface DataQualityDashboardViewProps {
  onNavigateToReview: (filterField?: string) => void;
}

export const DataQualityDashboardView: React.FC<DataQualityDashboardViewProps> = ({ onNavigateToReview }) => {
  const [data, setData] = useState<QualityDashboardData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMetrics = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getQualityDashboard();
      setData(res);
    } catch (err: any) {
      setError(err.message || 'Failed to load live quality dashboard metrics');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMetrics();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="flex flex-col items-center gap-3 text-[#5C554D]">
          <RefreshCw className="w-8 h-8 animate-spin text-[#E8622C]" />
          <span className="text-xs font-bold font-display">Loading Live Quality & Trust Telemetry...</span>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="bg-white/70 backdrop-blur-2xl rounded-3xl p-8 text-center border border-white/80 max-w-md mx-auto my-12 shadow-sm">
        <AlertTriangle className="w-8 h-8 text-[#E8622C] mx-auto mb-3" />
        <h3 className="font-display font-bold text-lg text-[#191715]">Telemetry Offline</h3>
        <p className="text-xs text-[#5C554D] mt-1">{error || 'Unable to connect to live telemetry service'}</p>
        <button
          onClick={fetchMetrics}
          className="mt-4 px-4 py-2 rounded-full bg-[#E8622C] text-white text-xs font-bold cursor-pointer"
        >
          Retry Connection
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Top Banner Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-white/70 backdrop-blur-2xl p-6 rounded-3xl border border-white/80 shadow-[0_8px_32px_rgba(26,23,21,0.04)]">
        <div>
          <div className="flex items-center gap-2">
            <span className="px-2.5 py-0.5 rounded-full bg-[#E8622C]/10 text-[#E8622C] text-[10px] font-mono font-bold uppercase tracking-wider border border-[#E8622C]/20">
              Phase 11 Production QA
            </span>
            <span className="text-xs text-[#8C8276] font-mono">Live Computed Telemetry</span>
          </div>
          <h1 className="font-didone font-bold text-2xl sm:text-3xl text-[#191715] mt-1">
            Data Quality & Trust Dashboard
          </h1>
          <p className="text-xs text-[#5C554D] mt-1">
            Catalog-wide verification, suspicious-fill anti-fabrication detection, and confidence health metrics.
          </p>
        </div>

        <button
          onClick={fetchMetrics}
          className="px-4 py-2 rounded-full bg-white/80 hover:bg-white text-[#191715] border border-white/80 text-xs font-bold flex items-center gap-2 shadow-2xs transition-all cursor-pointer"
        >
          <RefreshCw className="w-3.5 h-3.5 text-[#E8622C]" />
          <span>Refresh Live Data</span>
        </button>
      </div>

      {/* Hero Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white/70 backdrop-blur-2xl p-5 rounded-3xl border border-white/80 shadow-2xs space-y-1">
          <div className="flex items-center justify-between text-xs text-[#8C8276] font-bold uppercase tracking-wider">
            <span>Overall Catalog Confidence</span>
            <ShieldCheck className="w-4 h-4 text-[#1F8A53]" />
          </div>
          <div className="font-display font-bold text-3xl text-[#191715]">
            {data.confidence_overall_avg}%
          </div>
          <span className="text-[11px] text-[#5C554D] block">Min-weighted per-record trust</span>
        </div>

        <div className="bg-white/70 backdrop-blur-2xl p-5 rounded-3xl border border-white/80 shadow-2xs space-y-1">
          <div className="flex items-center justify-between text-xs text-[#8C8276] font-bold uppercase tracking-wider">
            <span>Auto-Committed Ratio</span>
            <CheckCircle2 className="w-4 h-4 text-[#E8622C]" />
          </div>
          <div className="font-display font-bold text-3xl text-[#191715]">
            {data.auto_committed_pct}%
          </div>
          <span className="text-[11px] text-[#5C554D] block">High confidence ($\ge$85%) verified</span>
        </div>

        <div className="bg-white/70 backdrop-blur-2xl p-5 rounded-3xl border border-white/80 shadow-2xs space-y-1">
          <div className="flex items-center justify-between text-xs text-[#8C8276] font-bold uppercase tracking-wider">
            <span>Needs Human Review</span>
            <AlertTriangle className="w-4 h-4 text-[#D45320]" />
          </div>
          <div className="font-display font-bold text-3xl text-[#D45320]">
            {data.needs_review_count}
          </div>
          <span className="text-[11px] text-[#5C554D] block">Low-conf or conflicting fields</span>
        </div>

        <div className="bg-white/70 backdrop-blur-2xl p-5 rounded-3xl border border-white/80 shadow-2xs space-y-1">
          <div className="flex items-center justify-between text-xs text-[#8C8276] font-bold uppercase tracking-wider">
            <span>Catalog Records Loaded</span>
            <FileText className="w-4 h-4 text-[#191715]" />
          </div>
          <div className="font-display font-bold text-3xl text-[#191715]">
            {data.total_records}
          </div>
          <span className="text-[11px] text-[#5C554D] block">From {data.total_sources} source docs</span>
        </div>
      </div>

      {/* Suspicious Fill Anti-Fabrication Section */}
      <div className="bg-white/70 backdrop-blur-2xl p-6 rounded-3xl border border-white/80 shadow-2xs space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-[#FDF2EC] text-[#E8622C] flex items-center justify-center border border-[#E8622C]/20">
              <AlertTriangle className="w-4 h-4" />
            </div>
            <div>
              <h2 className="font-display font-bold text-base text-[#191715]">
                Suspicious-Fill & Anti-Fabrication Detector
              </h2>
              <p className="text-xs text-[#5C554D]">
                Flags identifier and numeric fields showing uniform repetition (&gt;5% identical values across distinct SKUs).
              </p>
            </div>
          </div>
        </div>

        {data.suspicious_fill_alerts.length === 0 ? (
          <div className="p-4 rounded-2xl bg-[#EAF5EE] border border-[#1F8A53]/20 flex items-center gap-3 text-xs text-[#1F8A53]">
            <CheckCircle2 className="w-5 h-5 shrink-0" />
            <span className="font-medium">
              Zero suspicious uniform fill patterns detected. All numeric & identifier fields exhibit natural variance.
            </span>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {data.suspicious_fill_alerts.map((alert, idx) => (
              <div
                key={idx}
                className="p-4 rounded-2xl bg-[#FFF9F2] border border-[#F5C29B] shadow-2xs space-y-2 flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs font-bold text-[#E8622C]">
                      {alert.field_name}
                    </span>
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-[#E8622C]/15 text-[#D45320] border border-[#E8622C]/30">
                      {alert.repetition_share_pct}% Repetition ({alert.severity})
                    </span>
                  </div>
                  <div className="text-sm font-bold text-[#191715] font-display mt-1">
                    Value: "{alert.repeated_value}"
                  </div>
                  <p className="text-xs text-[#5C554D] mt-1 leading-relaxed">
                    {alert.recommendation}
                  </p>
                </div>

                <button
                  onClick={() => onNavigateToReview(alert.field_name.toLowerCase())}
                  className="mt-3 w-full py-2 rounded-xl bg-[#191715] hover:bg-[#E8622C] text-white text-xs font-bold flex items-center justify-center gap-1.5 transition-all cursor-pointer shadow-xs"
                >
                  <span>Inspect Affected Records in Review Queue</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Classification Diversity & Aging Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Classification Diversity */}
        <div className="bg-white/70 backdrop-blur-2xl p-6 rounded-3xl border border-white/80 shadow-2xs space-y-3">
          <div className="flex items-center gap-2 text-sm font-bold text-[#191715] font-display">
            <Layers className="w-4 h-4 text-[#E8622C]" />
            <span>Classification Diversity Health</span>
          </div>

          {data.classification_diversity_alerts.length === 0 ? (
            <p className="text-xs text-[#5C554D] leading-relaxed bg-white/60 p-4 rounded-2xl border border-white/80">
              Taxonomy classification exhibits healthy diversity across departments and classes. Zero category clustering bottlenecks detected.
            </p>
          ) : (
            <div className="space-y-2">
              {data.classification_diversity_alerts.map((divAlert, idx) => (
                <div key={idx} className="p-3.5 rounded-2xl bg-[#FFF9F2] border border-[#F5C29B] text-xs space-y-1">
                  <div className="flex items-center justify-between font-bold text-[#191715]">
                    <span>{divAlert.taxonomy_path}</span>
                    <span className="text-[#E8622C]">{divAlert.coverage_pct}% of Batch</span>
                  </div>
                  <p className="text-[#5C554D] text-[11px]">{divAlert.recommendation}</p>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Needs Review Aging */}
        <div className="bg-white/70 backdrop-blur-2xl p-6 rounded-3xl border border-white/80 shadow-2xs space-y-3">
          <div className="flex items-center gap-2 text-sm font-bold text-[#191715] font-display">
            <Clock className="w-4 h-4 text-[#E8622C]" />
            <span>Needs Review Aging Analysis</span>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="p-3 rounded-2xl bg-white/60 border border-white/80 text-center">
              <span className="text-[10px] font-bold text-[#8C8276] block uppercase tracking-wider">&lt; 1 Hour</span>
              <span className="font-display font-bold text-xl text-[#191715] mt-0.5 block">{data.aging_summary.less_than_1h}</span>
            </div>
            <div className="p-3 rounded-2xl bg-white/60 border border-white/80 text-center">
              <span className="text-[10px] font-bold text-[#8C8276] block uppercase tracking-wider">1h - 24h</span>
              <span className="font-display font-bold text-xl text-[#E8622C] mt-0.5 block">{data.aging_summary['1h_to_24h']}</span>
            </div>
            <div className="p-3 rounded-2xl bg-white/60 border border-white/80 text-center">
              <span className="text-[10px] font-bold text-[#8C8276] block uppercase tracking-wider">&gt; 24 Hours</span>
              <span className="font-display font-bold text-xl text-[#D45320] mt-0.5 block">{data.aging_summary.more_than_24h}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
