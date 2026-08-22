import React, { useState, useEffect, useRef } from 'react';
import { BackgroundVideo } from './components/BackgroundVideo';
import { TopNav } from './components/TopNav';
import { LeftRail } from './components/LeftRail';
import { DashboardView } from './components/DashboardView';
import { FieldInspectorView } from './components/FieldInspectorView';
import { ReviewQueueView } from './components/ReviewQueueView';
import { ProductsCatalogView } from './components/ProductsCatalogView';
import { IngestionSourcesView } from './components/IngestionSourcesView';
import { DataQualityDashboardView } from './components/DataQualityDashboardView';
import { CatalogCopilotView } from './components/CatalogCopilotView';
import { IngestModal } from './components/IngestModal';
import { INITIAL_PRODUCTS, INITIAL_SOURCES, CATEGORY_OVERVIEWS } from './data/mockData';
import { ProductRecord, IngestionSource, CategoryOverview, ActiveTab, FieldAuditEntry } from './types';
import { 
  fetchProducts, 
  fetchSources, 
  acceptField, 
  editField, 
  buildCategoryOverviews 
} from './lib/api';

import { ErrorBoundary } from './components/ErrorBoundary';
import { AuthProvider, useAuth } from './context/AuthContext';
import { AuthContainer } from './components/auth/AuthContainer';
import { VerifyEmailView } from './components/auth/VerifyEmailView';

export default function App() {
  return (
    <AuthProvider>
      <MainAppContent />
    </AuthProvider>
  );
}

function MainAppContent() {
  const { session, user, loading, isEmailVerified } = useAuth();

  const [products, setProducts] = useState<ProductRecord[]>([]);
  const [sources, setSources] = useState<IngestionSource[]>([]);
  const [categories, setCategories] = useState<CategoryOverview[]>([]);
  const [activeTab, setActiveTab] = useState<ActiveTab>('dashboard');
  const [selectedProduct, setSelectedProduct] = useState<ProductRecord | null>(null);
  const [isIngestModalOpen, setIsIngestModalOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLiveConnected, setIsLiveConnected] = useState(false);
  const mainScrollRef = useRef<HTMLElement | null>(null);

  // Load real-time catalog data from backend API
  useEffect(() => {
    let isMounted = true;

    async function loadBackendData() {
      try {
        const [liveProducts, liveSources] = await Promise.all([
          fetchProducts(),
          fetchSources(),
        ]);

        if (isMounted) {
          setIsLiveConnected(true);
          setProducts(liveProducts || []);
          setSources(liveSources || []);

          if (liveProducts && liveProducts.length > 0) {
            setSelectedProduct(prev => {
              if (!prev) return liveProducts[0];
              const match = liveProducts.find(p => p.id === prev.id);
              return match || prev;
            });
            setCategories(buildCategoryOverviews(liveProducts));
          } else {
            setSelectedProduct(null);
            setCategories([]);
          }
        }

      } catch (err) {
        console.info('Backend sync error:', err);
      }
    }

    loadBackendData();

    // Periodic real-time sync every 5 seconds
    const interval = setInterval(loadBackendData, 5000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  // Update categories and default selected product whenever products list changes
  useEffect(() => {
    if (products.length > 0) {
      setCategories(buildCategoryOverviews(products));
      setSelectedProduct(prev => {
        if (!prev) return products[0];
        const match = products.find(p => p.id === prev.id);
        return match || prev;
      });
    } else {
      setCategories([]);
      setSelectedProduct(null);
    }
  }, [products]);

  // Scroll to top when changing views
  useEffect(() => {
    if (mainScrollRef.current) {
      mainScrollRef.current.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }, [activeTab]);

  // Handle single product approval
  const handleApproveProduct = async (productId: string) => {
    const prodToApprove = products.find(p => p.id === productId);
    if (prodToApprove) {
      for (const field of prodToApprove.fields || []) {
        if (!field.isApproved) {
          acceptField(productId, field.id).catch(console.warn);
        }
      }
    }

    setProducts(prev => prev.map(p => {
      if (p.id === productId) {
        const approvalEntry: FieldAuditEntry = {
          id: `audit-batch-${Date.now()}`,
          timestamp: 'Just now',
          fieldId: 'f-all-approved',
          fieldName: 'All Attributes Verification',
          previousValue: `${p.fieldsReviewedCount}/${p.fieldsCount} Reviewed`,
          newValue: 'All Attributes Approved & Committed',
          changedBy: 'Lead Catalog Engineer',
          changeType: 'manual_override',
          confidenceBefore: p.confidence,
          confidenceAfter: 98,
          reason: 'Manual validation of extraction fields',
        };

        const updatedProd: ProductRecord = {
          ...p,
          status: 'human_corrected',
          confidence: 98,
          confidenceLevel: 'high',
          fieldsReviewedCount: p.fieldsCount,
          conflictsSummary: undefined,
          fields: (p.fields || []).map(f => ({ ...f, isApproved: true, confidence: 99 })),
          auditLog: [approvalEntry, ...(p.auditLog || [])]
        };

        if (selectedProduct && selectedProduct.id === productId) {
          setSelectedProduct(updatedProd);
        }

        return updatedProd;
      }
      return p;
    }));
  };

  // Handle bulk product approval
  const handleApproveAll = (productIds: string[]) => {
    productIds.forEach(id => handleApproveProduct(id));
  };

  // Handle field update in Field Inspector
  const handleUpdateField = async (productId: string, fieldId: string, newValue: string, isApproved: boolean) => {
    // Notify backend in real time
    if (isApproved) {
      editField(productId, fieldId, newValue).catch(console.warn);
    }

    setProducts(prev => prev.map(p => {
      if (p.id === productId) {
        const targetField = p.fields.find(f => f.id === fieldId);
        const prevValue = targetField?.value || '';
        const prevConfidence = targetField?.confidence || 75;
        const fieldName = targetField?.name || 'Specification Field';
        const isRevert = targetField?.originalValue === newValue && targetField.isCorrected;
        const isValueSame = prevValue === newValue;

        const updatedFields = p.fields.map(f => {
          if (f.id === fieldId) {
            return {
              ...f,
              value: newValue,
              originalValue: f.originalValue || f.value,
              isCorrected: !isValueSame || f.isCorrected,
              isApproved: isApproved,
              confidence: 99,
              confidenceLevel: 'high' as const
            };
          }
          return f;
        });

        const newConfidence = Math.round(
          updatedFields.reduce((acc, f) => acc + f.confidence, 0) / updatedFields.length
        );

        const newAuditEntry: FieldAuditEntry = {
          id: `audit-${Date.now()}-${Math.random().toString(36).substr(2, 4)}`,
          timestamp: 'Just now',
          fieldId,
          fieldName,
          previousValue: prevValue,
          newValue,
          changedBy: 'Lead Catalog Engineer',
          changeType: isRevert ? 'revert' : isValueSame ? 'verified_approval' : 'manual_override',
          confidenceBefore: prevConfidence,
          confidenceAfter: 99,
          reason: isValueSame 
            ? 'Verified canonical representation against OEM datasheet schema'
            : isRevert
            ? `Reverted field value back to "${newValue}"`
            : `Manual override of attribute value to "${newValue}"`,
          sourceRef: p.sourceDocument
        };

        const existingAuditLog = p.auditLog || [];

        const updatedProd: ProductRecord = {
          ...p,
          fields: updatedFields,
          confidence: newConfidence,
          confidenceLevel: newConfidence >= 85 ? 'high' : 'medium',
          status: updatedFields.every(f => f.isApproved) ? 'human_corrected' : p.status,
          fieldsReviewedCount: updatedFields.filter(f => f.isApproved || f.isCorrected).length,
          auditLog: [newAuditEntry, ...existingAuditLog]
        };

        if (selectedProduct && selectedProduct.id === productId) {
          setSelectedProduct(updatedProd);
        }

        return updatedProd;
      }
      return p;
    }));
  };

  // Handle approving all fields for currently inspected product
  const handleApproveAllFields = (productId: string) => {
    handleApproveProduct(productId);
    setSelectedProduct(prev => {
      if (!prev) return null;
      return {
        ...prev,
        status: 'human_corrected',
        confidence: 98,
        confidenceLevel: 'high',
        fieldsReviewedCount: prev.fieldsCount,
        conflictsSummary: undefined,
        fields: (prev.fields || []).map(f => ({ ...f, isApproved: true, confidence: 99 }))
      };
    });
  };

  // Handle newly ingested source
  const handleIngestSuccess = (newProduct: ProductRecord, newSource: IngestionSource) => {
    setProducts(prev => [newProduct, ...prev]);
    setSources(prev => [newSource, ...prev]);
    setSelectedProduct(newProduct);
    setActiveTab('field_inspector');
  };

  const reviewQueueCount = (products || []).filter(p => p.status === 'needs_review' || p.status === 'flagged_conflict').length;

  // 1. Loading state during session restoration
  if (loading) {
    return (
      <div className="relative h-screen w-full bg-[#F5E9D8] text-[#191715] flex flex-col items-center justify-center font-sans">
        <BackgroundVideo />
        <div className="relative z-10 flex flex-col items-center gap-3 p-6 rounded-3xl bg-white/70 backdrop-blur-2xl border border-white/80 shadow-lg">
          <div className="w-10 h-10 border-3 border-[#E8622C] border-t-transparent rounded-full animate-spin" />
          <p className="text-xs font-bold text-[#191715]">Authenticating Session...</p>
        </div>
      </div>
    );
  }

  // 2. Unauthenticated user -> render Auth Flow (SignIn, SignUp, ForgotPassword, ResetPassword)
  if (!session || !user) {
    return <AuthContainer />;
  }

  // 3. Authenticated BUT email not verified -> render VerifyEmailView block
  if (!isEmailVerified) {
    return <VerifyEmailView />;
  }

  // 4. Authenticated & Email Verified -> Render Protected SourceLedger Application
  return (
    <div className="relative h-screen w-full bg-[#F5E9D8] text-[#191715] flex flex-col font-sans selection:bg-[#E8622C] selection:text-white overflow-hidden">
      {/* Background Abstract Shapes Video */}
      <BackgroundVideo />

      {/* Top Bar Navigation */}
      <TopNav
        onOpenIngestModal={() => setIsIngestModalOpen(true)}
        onSelectProduct={(p) => setSelectedProduct(p)}
        products={products}
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
      />

      {/* Main Layout: Left Icon Rail + Content Area */}
      <div className="relative z-10 flex flex-1 overflow-hidden min-h-0 w-full">
        <LeftRail
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          reviewQueueCount={reviewQueueCount}
        />

        <main
          id="main-content-scroll"
          ref={mainScrollRef}
          className="flex-1 h-full overflow-y-auto overflow-x-hidden min-h-0 w-full focus:outline-hidden"
        >
          <div className="px-4 sm:px-6 md:px-8 lg:px-10 py-6 w-full max-w-[1920px] mx-auto">
            <ErrorBoundary>
              {activeTab === 'dashboard' && (
                <DashboardView
                  products={products}
                  sources={sources}
                  categories={categories}
                  onSelectProduct={(p) => setSelectedProduct(p)}
                  onApproveProduct={handleApproveProduct}
                  onOpenIngestModal={() => setIsIngestModalOpen(true)}
                  onNavigateToTab={(tab) => setActiveTab(tab)}
                />
              )}

              {activeTab === 'quality_dashboard' && (
                <DataQualityDashboardView
                  onNavigateToReview={() => setActiveTab('review_queue')}
                />
              )}

              {activeTab === 'field_inspector' && (
                <FieldInspectorView
                  product={selectedProduct!}
                  products={products}
                  onSelectProduct={(p) => setSelectedProduct(p)}
                  onUpdateField={handleUpdateField}
                  onApproveAllFields={handleApproveAllFields}
                  onBackToDashboard={() => setActiveTab('dashboard')}
                />
              )}

              {activeTab === 'review_queue' && (
                <ReviewQueueView
                  products={products}
                  onSelectProduct={(p) => setSelectedProduct(p)}
                  onApproveProduct={handleApproveProduct}
                  onApproveAll={handleApproveAll}
                  onNavigateToTab={(tab) => setActiveTab(tab)}
                />
              )}

              {activeTab === 'catalog' && (
                <ProductsCatalogView
                  products={products}
                  onSelectProduct={(p) => setSelectedProduct(p)}
                  onNavigateToTab={(tab) => setActiveTab(tab)}
                />
              )}

              {activeTab === 'sources' && (
                <IngestionSourcesView
                  sources={sources}
                  onOpenIngestModal={() => setIsIngestModalOpen(true)}
                />
              )}

              {activeTab === 'copilot' && (
                <CatalogCopilotView
                  onSelectProduct={(sku) => {
                    const match = products.find((p) => (p.sku || p.name).toLowerCase() === sku.toLowerCase());
                    if (match) {
                      setSelectedProduct(match);
                      setActiveTab('field_inspector');
                    } else {
                      setActiveTab('catalog');
                    }
                  }}
                />
              )}

              {activeTab === 'settings' && (
                <SettingsView />
              )}

              {activeTab === 'ocr' && (
                <OcrAgentView />
              )}
            </ErrorBoundary>

          </div>
        </main>
      </div>

      {/* Modal for Ingesting New Datasheets / CSVs */}
      <IngestModal
        isOpen={isIngestModalOpen}
        onClose={() => setIsIngestModalOpen(false)}
        onIngestSuccess={handleIngestSuccess}
      />
    </div>
  );
}
