import React, { useState, useRef, useEffect } from 'react';
import { 
  X, 
  UploadCloud, 
  Sparkles, 
  CheckCircle2, 
  ArrowRight,
  AlertCircle,
  FileText,
  Globe,
  FileType,
  Plus,
  ScanText
} from 'lucide-react';
import { ProductRecord, IngestionSource } from '../types';
import { ingestSource as apiIngestSource, mapOcrResultToProductRecord } from '../lib/api';
import { supabase } from '../lib/supabase';

interface IngestModalProps {
  isOpen: boolean;
  onClose: () => void;
  onIngestSuccess: (newProduct: ProductRecord, newSource: IngestionSource) => void;
}

export const IngestModal: React.FC<IngestModalProps> = ({
  isOpen,
  onClose,
  onIngestSuccess
}) => {
  const [activeTab, setActiveTab] = useState<'upload' | 'text' | 'ocr'>('upload');
  const [content, setContent] = useState('');
  const [filename, setFilename] = useState('');
  const [sourceType, setSourceType] = useState<'web' | 'pdf'>('web');
  const [categoryKey, setCategoryKey] = useState<string>('');
  const [trustTier, setTrustTier] = useState<number>(1);
  const [isProcessing, setIsProcessing] = useState(false);
  const [processStep, setProcessStep] = useState<number>(0);
  const [extractedPreview, setExtractedPreview] = useState<ProductRecord | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // OCR specific state
  const [ocrFile, setOcrFile] = useState<File | null>(null);
  const [ocrPreviewUrl, setOcrPreviewUrl] = useState<string | null>(null);
  const [ocrDocType, setOcrDocType] = useState<string>('receipt_invoice');
  const [enableRefinement, setEnableRefinement] = useState<boolean>(true);
  const ocrFileInputRef = useRef<HTMLInputElement | null>(null);

  const resetModalState = () => {
    setExtractedPreview(null);
    setIsProcessing(false);
    setProcessStep(0);
    setContent('');
    setFilename('');
    setErrorMsg(null);
    setCategoryKey('');
    setActiveTab('upload');
    setSourceType('web');
    setTrustTier(1);
    setOcrFile(null);
    setOcrPreviewUrl(null);
    setOcrDocType('receipt_invoice');
    setEnableRefinement(true);
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (ocrFileInputRef.current) ocrFileInputRef.current.value = '';
  };

  useEffect(() => {
    if (isOpen) {
      resetModalState();
    }
  }, [isOpen]);

  const handleClose = () => {
    resetModalState();
    onClose();
  };

  if (!isOpen) return null;

  const samplePresets = [
    {
      name: 'Grundfos CR 15-3 Inline Centrifugal Pump',
      fileName: 'Grundfos_CR15_Datasheet.pdf',
      category: 'Industrial',
      categoryKey: 'industrial_pump',
      content: `GRUNDFOS CENTRIFUGAL PUMP CR 15-3 A-F-A-E-HQQE
Product Name: Grundfos CR 15-3 Vertical Multistage Pump
Flow Rate (Nominal): 15.0 m3/h
Rated Head: 45.2 m
Maximum Operating Pressure: 16 bar
Liquid Temperature Range: -20°C to +120°C
Motor Power: 3.0 kW
Pump Housing: Cast Iron EN-GJL-200
Impeller: Stainless Steel AISI 304`
    },
    {
      name: 'TE Connectivity AMPSEAL 16 8-Pin Connector',
      fileName: 'TE_AMPSEAL16_776495_1.pdf',
      category: 'Electronics',
      categoryKey: 'electrical_connector',
      content: `TE CONNECTIVITY AMPSEAL 16 8-POSITION CONNECTOR
Product Name: TE Connectivity AMPSEAL 16 8-Pin Plug Assembly
Part Number: 776495-1
Number of Positions: 8 Positions
Current Rating (Max): 13.0 A per contact
Operating Voltage: 250 V AC
Ingress Protection: IP67 and IP69K
Operating Temperature: -40°C to +125°C`
    },
    {
      name: 'Fabory M12x50 Class 10.9 Hex Bolt',
      fileName: 'Fabory_M12x50_Fastener.pdf',
      category: 'Industrial',
      categoryKey: 'safety_fastener',
      content: `FABORY M12 x 50mm CLASS 10.9 HEXAGON HEAD BOLT
Product Name: Fabory M12x50 Hex Head Cap Screw Class 10.9
Thread Size: M12 x 1.75 mm Pitch
Nominal Length: 50.0 mm
Property Class: Class 10.9
Proof Load Strength: 830 MPa
Tensile Strength (Min): 1040 MPa
Material Grade: Alloy Steel, Quenched and Tempered`
    }
  ];

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const lowerName = file.name.toLowerCase();
    const isImage = file.type.startsWith('image/') || /\.(png|jpe?g|webp|bmp|gif|tiff?)$/.test(lowerName);

    if (isImage) {
      setActiveTab('ocr');
      handleOcrFileChange(file);
      return;
    }

    setFilename(file.name);
    setErrorMsg(null);

    const validExtensions = ['.pdf', '.csv', '.txt', '.json', '.html', '.md', '.xlsx', '.xls'];
    const isValid = validExtensions.some(ext => lowerName.endsWith(ext));

    if (!isValid) {
      setErrorMsg(`Unsupported file type: ${file.name}. Please upload a PDF, Excel, CSV, Image, or Text file.`);
      return;
    }

    const isPdf = file.type === 'application/pdf' || lowerName.endsWith('.pdf');
    const isExcel = lowerName.endsWith('.xlsx') || lowerName.endsWith('.xls');
    const reader = new FileReader();

    if (isPdf) {
      setSourceType('pdf');
      reader.onload = () => {
        const result = reader.result as string;
        const base64 = result.includes(',') ? result.split(',')[1] : result;
        setContent(base64);
      };
      reader.readAsDataURL(file);
    } else if (isExcel) {
      setSourceType('xlsx' as any); // cast to any to bypass strict type if missing
      reader.onload = () => {
        const result = reader.result as string;
        const base64 = result.includes(',') ? result.split(',')[1] : result;
        setContent(base64);
      };
      reader.readAsDataURL(file);
    } else {
      setSourceType('web');
      reader.onload = () => {
        setContent(reader.result as string);
      };
      reader.readAsText(file);
    }
  };

  const handleOcrFileChange = (file: File | null) => {
    if (!file) return;
    const lowerName = file.name.toLowerCase();
    const isPdf = file.type === 'application/pdf' || lowerName.endsWith('.pdf');
    const isImage = file.type.startsWith('image/') || /\.(png|jpe?g|webp|bmp|gif|tiff?)$/.test(lowerName);

    if (!isPdf && !isImage) {
      setErrorMsg('Please select a valid document PDF or image file (PDF, PNG, JPEG, WEBP, BMP, GIF, TIFF).');
      return;
    }
    setErrorMsg(null);
    setOcrFile(file);

    if (isImage) {
      const reader = new FileReader();
      reader.onload = (e) => setOcrPreviewUrl(e.target?.result as string);
      reader.readAsDataURL(file);
    } else {
      setOcrPreviewUrl(null);
    }
  };

  const handleSelectPreset = (preset: typeof samplePresets[0]) => {
    setActiveTab('text');
    setContent(preset.content);
    setFilename(preset.fileName);
    setCategoryKey(preset.categoryKey);
    setSourceType('web');
  };

  const handleSubmitIngestion = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!content.trim()) {
      setErrorMsg('Please select a file or enter specification text to ingest.');
      return;
    }

    setIsProcessing(true);
    setErrorMsg(null);
    setProcessStep(1);

    const stepInterval1 = setTimeout(() => setProcessStep(2), 600);
    const stepInterval2 = setTimeout(() => setProcessStep(3), 1200);

    try {
      const realProduct = await apiIngestSource({
        sourceType,
        content: content.trim(),
        category: categoryKey || undefined,
        trustTier,
        filename: filename || (sourceType === 'pdf' ? 'datasheet.pdf' : 'spec_sheet.txt'),
      });

      clearTimeout(stepInterval1);
      clearTimeout(stepInterval2);
      setProcessStep(4);

      const realSource: IngestionSource = {
        id: `src-${Date.now()}`,
        name: filename || realProduct.name,
        fileName: filename || `${realProduct.name.replace(/\s+/g, '_')}.pdf`,
        fileType: sourceType === 'pdf' ? 'PDF Datasheet' : 'Web Scraper',
        fileSize: `${Math.max(1, Math.round(content.length / 1024))} KB`,
        recordsCount: 1,
        extractedFieldsCount: realProduct.fields.length,
        status: 'completed',
        avgConfidence: realProduct.confidence,
        category: realProduct.category,
        timestamp: 'Just now',
        processingTimeSec: 1.8,
        aiModelUsed: 'Ledger 3.6 Flash Multi-Agent Pipeline',
      };

      setExtractedPreview(realProduct);
      setIsProcessing(false);
      onIngestSuccess(realProduct, realSource);
    } catch (err) {
      clearTimeout(stepInterval1);
      clearTimeout(stepInterval2);
      setIsProcessing(false);
      setErrorMsg(err instanceof Error ? err.message : 'Ingestion failed');
    }
  };

  const handleOcrSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ocrFile) {
      setErrorMsg('Please select or drop a document image file to ingest.');
      return;
    }

    setIsProcessing(true);
    setErrorMsg(null);
    setProcessStep(1);

    const stepInterval1 = setTimeout(() => setProcessStep(2), 600);
    const stepInterval2 = setTimeout(() => setProcessStep(3), 1200);

    try {
      const formData = new FormData();
      formData.append('file', ocrFile);
      formData.append('document_type', ocrDocType);
      formData.append('enable_refinement', enableRefinement.toString());

      const { data: { session } } = await supabase.auth.getSession();
      const currentUserId = session?.user?.id || session?.user?.email;
      const headers: Record<string, string> = {};
      if (currentUserId) {
        headers['x-user-id'] = currentUserId;
      }

      const res = await fetch('/api/extract', {
        method: 'POST',
        headers,
        body: formData,
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Vision OCR Extraction failed');
      }

      const data = await res.json();
      clearTimeout(stepInterval1);
      clearTimeout(stepInterval2);
      setProcessStep(4);

      const { product: realProduct, source: realSource } = mapOcrResultToProductRecord(
        data,
        ocrFile.name,
        ocrDocType,
        trustTier
      );

      setExtractedPreview(realProduct);
      setIsProcessing(false);
      onIngestSuccess(realProduct, realSource);
    } catch (err: any) {
      clearTimeout(stepInterval1);
      clearTimeout(stepInterval2);
      setIsProcessing(false);
      setErrorMsg(err.message || 'Vision OCR Ingestion failed');
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-[#191715]/40 backdrop-blur-md flex items-center justify-center p-4 overflow-y-auto">
      <div className="bg-white/85 backdrop-blur-2xl rounded-3xl max-w-xl w-full p-6 sm:p-8 shadow-[0_20px_60px_rgba(0,0,0,0.18)] border border-white/90 ring-1 ring-white/60 relative my-8 animate-in fade-in zoom-in-95 duration-150">
        {/* Close Button */}
        <button
          onClick={handleClose}
          className="absolute top-6 right-6 p-2 rounded-full bg-white/70 hover:bg-white backdrop-blur-md text-[#8C8276] hover:text-[#191715] border border-white/80 shadow-2xs transition-colors cursor-pointer z-10"
        >
          <X className="w-4 h-4" />
        </button>

        {/* Modal Header */}
        <div className="mb-5">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/80 backdrop-blur-md text-[#E8622C] text-xs font-bold uppercase tracking-wider mb-2 border border-white/80 shadow-2xs">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Ledger Multi-Agent Ingestion Engine</span>
          </div>
          <h2 className="font-didone font-bold text-2xl text-[#191715] tracking-tight">
            Ingest Product <span className="font-didone-italic text-[#E8622C] font-normal">Datasheet</span>
          </h2>
          <p className="text-xs text-[#5C554D] mt-1 leading-relaxed">
            Upload PDF files, CSV catalogs, paste specification text, or run vision OCR. Ledger will extract schema-locked fields with source citations in real time.
          </p>
        </div>

        {errorMsg && (
          <div className="mb-4 p-3 rounded-2xl bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2">
            <AlertCircle size={16} className="shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {!isProcessing && !extractedPreview ? (
          <div className="space-y-5">
            {/* Ingestion Mode Pill Switcher - 3 Equal Tabs */}
            <div className="flex bg-white/60 backdrop-blur-md p-1 rounded-2xl border border-white/80 shadow-2xs text-xs gap-1">
              <button
                type="button"
                onClick={() => { setActiveTab('upload'); setSourceType('pdf'); }}
                className={`flex-1 py-2 px-2.5 rounded-xl font-bold flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
                  activeTab === 'upload' ? 'bg-[#191715] text-white shadow-xs' : 'text-[#5C554D] hover:text-[#191715]'
                }`}
              >
                <UploadCloud size={14} />
                <span className="truncate">Upload PDF / File</span>
              </button>
              <button
                type="button"
                onClick={() => { setActiveTab('text'); setSourceType('web'); }}
                className={`flex-1 py-2 px-2.5 rounded-xl font-bold flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
                  activeTab === 'text' ? 'bg-[#191715] text-white shadow-xs' : 'text-[#5C554D] hover:text-[#191715]'
                }`}
              >
                <Globe size={14} />
                <span className="truncate">Paste Text / Spec URL</span>
              </button>
              <button
                type="button"
                onClick={() => { setActiveTab('ocr'); }}
                className={`flex-1 py-2 px-2.5 rounded-xl font-bold flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
                  activeTab === 'ocr' ? 'bg-[#E8622C] text-white shadow-xs' : 'text-[#5C554D] hover:text-[#191715]'
                }`}
              >
                <ScanText size={14} />
                <span className="truncate">Ledger Multimodal OCR</span>
              </button>
            </div>

            {/* Ingestion Inputs */}
            {activeTab === 'ocr' ? (
              <form onSubmit={handleOcrSubmit} className="space-y-4">
                <input
                  ref={ocrFileInputRef}
                  type="file"
                  accept=".pdf,.png,.jpg,.jpeg,.webp,.bmp,.gif,.tiff,image/*,application/pdf"
                  onChange={(e) => e.target.files && handleOcrFileChange(e.target.files[0])}
                  className="hidden"
                />

                {/* File Dropzone for PDF or Image */}
                <div
                  onClick={() => ocrFileInputRef.current?.click()}
                  className="border-2 border-dashed border-white/90 hover:border-[#E8622C] bg-white/50 backdrop-blur-md hover:bg-white/80 rounded-3xl p-6 text-center shadow-inner transition-all cursor-pointer group"
                >
                  {ocrFile ? (
                    ocrPreviewUrl ? (
                      <div className="space-y-2">
                        <img
                          src={ocrPreviewUrl}
                          alt="OCR Document Preview"
                          className="max-h-36 mx-auto rounded-xl object-contain shadow-xs border border-white/80"
                        />
                        <p className="font-display font-bold text-xs text-[#191715] truncate">
                          Selected Image: {ocrFile.name}
                        </p>
                        <span className="text-[11px] text-[#E8622C] underline">Click or drop to change file</span>
                      </div>
                    ) : (
                      <div className="space-y-2 py-2">
                        <div className="w-12 h-12 rounded-2xl bg-[#E8622C]/10 text-[#E8622C] mx-auto flex items-center justify-center border border-[#E8622C]/20 shadow-xs">
                          <FileType className="w-6 h-6" />
                        </div>
                        <p className="font-display font-bold text-sm text-[#191715] truncate">
                          Selected PDF: {ocrFile.name}
                        </p>
                        <p className="text-xs text-[#8C8276]">
                          {Math.round(ocrFile.size / 1024)} KB — Multi-page PDF page screenshots will be rendered & extracted
                        </p>
                        <span className="text-[11px] text-[#E8622C] underline">Click or drop to change PDF</span>
                      </div>
                    )
                  ) : (
                    <>
                      <div className="w-12 h-12 rounded-2xl bg-white/90 backdrop-blur-md shadow-xs mx-auto flex items-center justify-center text-[#E8622C] group-hover:scale-110 border border-white/80 transition-transform">
                        <FileType className="w-6 h-6" />
                      </div>
                      <p className="font-display font-bold text-sm text-[#191715] mt-3">
                        Click or drop PDF document or photo/image here
                      </p>
                      <p className="text-xs text-[#8C8276] mt-0.5">
                        Supports Multi-Page PDFs, PNG, JPEG, WEBP, BMP, GIF, TIFF
                      </p>
                    </>
                  )}
                </div>

                {/* Document Extraction Schema & Trust Tier */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="text-[11px] font-bold uppercase tracking-wider text-[#8C8276] block mb-1">
                      Extraction Schema
                    </label>
                    <select
                      value={ocrDocType}
                      onChange={(e) => setOcrDocType(e.target.value)}
                      className="w-full bg-white/60 backdrop-blur-md text-xs font-semibold text-[#191715] p-2.5 rounded-xl border border-white/80 shadow-2xs focus:outline-hidden cursor-pointer"
                    >
                      <option value="receipt_invoice">🧾 Receipt / Invoice Schema</option>
                      <option value="general">📄 General Key-Values & Document</option>
                      <option value="id_card">🪪 ID Card / License / Passport</option>
                      <option value="table">📊 Table Data (Headers & Rows)</option>
                      <option value="form">📝 Form Fields & Checkboxes</option>
                    </select>
                  </div>

                  <div>
                    <label className="text-[11px] font-bold uppercase tracking-wider text-[#8C8276] block mb-1">
                      Source Trust Tier
                    </label>
                    <select
                      value={trustTier}
                      onChange={(e) => setTrustTier(Number(e.target.value))}
                      className="w-full bg-white/60 backdrop-blur-md text-xs font-semibold text-[#191715] p-2.5 rounded-xl border border-white/80 shadow-2xs focus:outline-hidden cursor-pointer"
                    >
                      <option value={1}>Tier 1: OEM / Manufacturer Spec</option>
                      <option value={2}>Tier 2: Authorized Distributor</option>
                      <option value={3}>Tier 3: Third-Party Catalog</option>
                    </select>
                  </div>
                </div>

                {/* Self-Correction Loop Toggle */}
                <div className="flex items-center justify-between p-3 rounded-xl bg-white/50 border border-white/80">
                  <div className="space-y-0.5">
                    <span className="text-xs font-bold text-[#191715] flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-[#E8622C]" />
                      Agent Tool Self-Correction Loop
                    </span>
                    <p className="text-[11px] text-[#8C8276]">
                      Re-audits vision extraction against document math schemas
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setEnableRefinement(!enableRefinement)}
                    className={`w-10 h-5 flex items-center rounded-full p-0.5 transition-colors cursor-pointer ${
                      enableRefinement ? 'bg-[#E8622C]' : 'bg-[#191715]/20'
                    }`}
                  >
                    <div
                      className={`bg-white w-4 h-4 rounded-full shadow-xs transform transition-transform ${
                        enableRefinement ? 'translate-x-5' : 'translate-x-0'
                      }`}
                    />
                  </button>
                </div>

                {/* Action Button matching other tabs */}
                <button
                  type="submit"
                  disabled={!ocrFile || isProcessing}
                  className="w-full py-3.5 px-6 rounded-full bg-gradient-to-r from-[#E8622C] to-[#D45320] hover:scale-[1.01] active:scale-[0.99] text-white text-xs font-bold shadow-md shadow-[#E8622C]/25 border border-white/20 flex items-center justify-center gap-2 transition-all disabled:opacity-50 cursor-pointer"
                >
                  <span>Ingest & Extract Provenance</span>
                  <ArrowRight size={16} />
                </button>
              </form>
            ) : (
              <form onSubmit={handleSubmitIngestion} className="space-y-5">
                {activeTab === 'upload' ? (
                  <div>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".pdf,.txt,.csv,.json"
                      onChange={handleFileUpload}
                      className="hidden"
                    />
                    <div
                      onClick={() => fileInputRef.current?.click()}
                      className="border-2 border-dashed border-white/90 hover:border-[#E8622C] bg-white/50 backdrop-blur-md hover:bg-white/80 rounded-3xl p-6 text-center shadow-inner transition-all cursor-pointer group"
                    >
                      <div className="w-12 h-12 rounded-2xl bg-white/90 backdrop-blur-md shadow-xs mx-auto flex items-center justify-center text-[#E8622C] group-hover:scale-110 border border-white/80 transition-transform">
                        <FileType className="w-6 h-6" />
                      </div>
                      <p className="font-display font-bold text-sm text-[#191715] mt-3">
                        {filename ? `Selected: ${filename}` : 'Click or drop PDF, TXT, CSV file here'}
                      </p>
                      <p className="text-xs text-[#8C8276] mt-0.5">
                        {content ? `${Math.round(content.length / 1024)} KB loaded ready for extraction` : 'Supports technical datasheets up to 50MB'}
                      </p>
                    </div>
                  </div>
                ) : (
                  <div>
                    <label className="text-[11px] font-bold uppercase tracking-wider text-[#8C8276] block mb-1.5">
                      Specification Text or Product URL
                    </label>
                    <textarea
                      rows={4}
                      value={content}
                      onChange={(e) => { setContent(e.target.value); setSourceType('web'); }}
                      placeholder="Paste technical specification text, datasheet tables, or product page URL..."
                      className="w-full text-xs font-mono bg-white/60 backdrop-blur-md p-3.5 rounded-2xl border border-white/80 focus:outline-hidden focus:border-[#E8622C] focus:bg-white shadow-2xs text-[#191715] placeholder:text-[#8C8276] leading-relaxed resize-none"
                      required
                    />
                  </div>
                )}

                {/* Category Schema Selector & Trust Tier */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="text-[11px] font-bold uppercase tracking-wider text-[#8C8276] block mb-1">
                      Category Schema
                    </label>
                    <select
                      value={categoryKey}
                      onChange={(e) => setCategoryKey(e.target.value)}
                      className="w-full bg-white/60 backdrop-blur-md text-xs font-semibold text-[#191715] p-2.5 rounded-xl border border-white/80 shadow-2xs focus:outline-hidden cursor-pointer"
                    >
                      <option value="">Auto-Detect Category Schema</option>
                      <option value="industrial_pump">Industrial Pump Schema</option>
                      <option value="electrical_connector">Electrical Connector Schema</option>
                      <option value="safety_fastener">Safety Fastener Schema</option>
                    </select>
                  </div>

                  <div>
                    <label className="text-[11px] font-bold uppercase tracking-wider text-[#8C8276] block mb-1">
                      Source Trust Tier
                    </label>
                    <select
                      value={trustTier}
                      onChange={(e) => setTrustTier(Number(e.target.value))}
                      className="w-full bg-white/60 backdrop-blur-md text-xs font-semibold text-[#191715] p-2.5 rounded-xl border border-white/80 shadow-2xs focus:outline-hidden cursor-pointer"
                    >
                      <option value={1}>Tier 1: OEM / Manufacturer Spec</option>
                      <option value={2}>Tier 2: Authorized Distributor</option>
                      <option value={3}>Tier 3: Third-Party Catalog</option>
                    </select>
                  </div>
                </div>

                {/* Sample Presets */}
                <div>
                  <span className="text-[11px] font-bold uppercase tracking-wider text-[#8C8276] block mb-2">
                    Or fill with a sample datasheet:
                  </span>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    {samplePresets.map((preset, idx) => (
                      <button
                        key={idx}
                        type="button"
                        onClick={() => handleSelectPreset(preset)}
                        className="text-left p-2.5 rounded-xl bg-white/60 hover:bg-white backdrop-blur-md border border-white/80 shadow-2xs transition-colors cursor-pointer text-xs"
                      >
                        <span className="font-bold text-[#191715] truncate block">
                          {preset.category}
                        </span>
                        <span className="text-[10px] text-[#8C8276] truncate block mt-0.5">
                          {preset.fileName}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Submit Action Button */}
                <button
                  type="submit"
                  disabled={!content.trim() || isProcessing}
                  className="w-full py-3.5 px-6 rounded-full bg-gradient-to-r from-[#E8622C] to-[#D45320] hover:scale-[1.01] active:scale-[0.99] text-white text-xs font-bold shadow-md shadow-[#E8622C]/25 border border-white/20 flex items-center justify-center gap-2 transition-all disabled:opacity-50 cursor-pointer"
                >
                  <span>Ingest & Extract Provenance</span>
                  <ArrowRight size={16} />
                </button>
              </form>
            )}
          </div>   ) : isProcessing ? (
          /* Live AI Pipeline Steps Indicator */
          <div className="py-8 space-y-6">
            <div className="text-center">
              <div className="w-12 h-12 rounded-2xl bg-[#E8622C] text-white mx-auto flex items-center justify-center animate-bounce shadow-lg shadow-[#E8622C]/30">
                <Sparkles className="w-6 h-6" />
              </div>
              <h3 className="font-display font-bold text-lg text-[#191715] mt-3">
                Processing Datasheet through Ledger Pipeline...
              </h3>
              <p className="text-xs text-[#8C8276] mt-0.5">
                Ledger 3.6 Flash Multi-Agent Extraction Active
              </p>
            </div>

            {/* Progress Checklist */}
            <div className="space-y-3 bg-white/60 backdrop-blur-md p-4 rounded-2xl border border-white/80 shadow-2xs">
              <div className="flex items-center gap-3 text-xs">
                <div className={`w-5 h-5 rounded-full flex items-center justify-center ${
                  processStep >= 1 ? 'bg-[#1F8A53] text-white' : 'bg-white/60 text-[#8C8276]'
                }`}>
                  <CheckCircle2 className="w-3.5 h-3.5" />
                </div>
                <span className={processStep >= 1 ? 'font-bold text-[#191715]' : 'text-[#8C8276]'}>
                  Ingestion & Content Provenance Hashing
                </span>
              </div>

              <div className="flex items-center gap-3 text-xs">
                <div className={`w-5 h-5 rounded-full flex items-center justify-center ${
                  processStep >= 2 ? 'bg-[#1F8A53] text-white' : 'bg-white/60 text-[#8C8276]'
                }`}>
                  <CheckCircle2 className="w-3.5 h-3.5" />
                </div>
                <span className={processStep >= 2 ? 'font-bold text-[#191715]' : 'text-[#8C8276]'}>
                  Schema-Locked Attribute Extraction (Ledger 3.6 Flash)
                </span>
              </div>

              <div className="flex items-center gap-3 text-xs">
                <div className={`w-5 h-5 rounded-full flex items-center justify-center ${
                  processStep >= 3 ? 'bg-[#1F8A53] text-white' : 'bg-white/60 text-[#8C8276]'
                }`}>
                  <CheckCircle2 className="w-3.5 h-3.5" />
                </div>
                <span className={processStep >= 3 ? 'font-bold text-[#191715]' : 'text-[#8C8276]'}>
                  Confidence Scoring & Validation Gate
                </span>
              </div>
            </div>
          </div>
        ) : (
          /* Success Screen */
          <div className="text-center py-6 space-y-4">
            <div className="w-12 h-12 rounded-full bg-[#EAF5EE]/90 backdrop-blur-md text-[#1F8A53] border border-[#1F8A53]/20 mx-auto flex items-center justify-center shadow-xs">
              <CheckCircle2 className="w-6 h-6" />
            </div>
            <div>
              <h3 className="font-display font-black text-xl text-[#191715]">
                Source Successfully Ingested!
              </h3>
              <p className="text-xs text-[#5C554D] mt-1">
                <strong>{extractedPreview?.name}</strong> has been extracted and ledgered into your catalog with {extractedPreview?.confidence}% confidence.
              </p>
            </div>
            <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
              <button
                onClick={handleClose}
                className="px-5 py-2.5 rounded-full bg-gradient-to-r from-[#E8622C] to-[#D45320] hover:scale-[1.02] text-white font-bold text-xs shadow-md shadow-[#E8622C]/25 border border-white/20 transition-all cursor-pointer"
              >
                Open in Field Inspector
              </button>
              <button
                type="button"
                onClick={resetModalState}
                className="px-5 py-2.5 rounded-full bg-white hover:bg-[#FAF4EB] text-[#191715] font-bold text-xs shadow-xs border border-[#DFCDBC] transition-all cursor-pointer flex items-center gap-1.5"
              >
                <Plus className="w-4 h-4 text-[#E8622C]" />
                <span>Ingest Another Source</span>
              </button>
              <a
                href="http://localhost:8000/api/export/csv"
                download="Unihack_Delivery_Format.csv"
                className="px-5 py-2.5 rounded-full bg-white hover:bg-[#FAF4EB] text-[#191715] font-bold text-xs shadow-xs border border-[#DFCDBC] transition-all cursor-pointer flex items-center gap-1.5"
              >
                <FileText className="w-4 h-4 text-[#E8622C]" />
                <span>Export Delivery CSV</span>
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
