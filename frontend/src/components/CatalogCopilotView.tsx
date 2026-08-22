import React, { useState, useEffect, useRef } from 'react';
import { 
  Bot, 
  Send, 
  Sparkles, 
  ShieldCheck, 
  GitFork, 
  FileText, 
  Search, 
  Database, 
  ArrowRight, 
  Loader2,
  ChevronDown,
  ChevronUp,
  Cpu,
  Layers
} from 'lucide-react';
import { sendCopilotMessage, getCopilotSuggestions, CopilotResponse } from '../lib/api';

interface CatalogCopilotViewProps {
  onSelectProduct?: (sku: string) => void;
}

interface MessageItem {
  id: string;
  sender: 'user' | 'copilot';
  timestamp: string;
  data?: CopilotResponse;
  text?: string;
  isLoading?: boolean;
}

export const CatalogCopilotView: React.FC<CatalogCopilotViewProps> = ({ onSelectProduct }) => {
  const [inputPrompt, setInputPrompt] = useState('');
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [suggestions, setSuggestions] = useState<Array<{ label: string; prompt: string; icon: string }>>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [expandedTools, setExpandedTools] = useState<Record<string, boolean>>({});

  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Load initial suggestions
    getCopilotSuggestions()
      .then((suggs) => setSuggestions(suggs))
      .catch(() => {});

    // Welcome message
    setMessages([
      {
        id: 'welcome-1',
        sender: 'copilot',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        data: {
          question: 'Welcome',
          answer: `### 👋 Welcome to SourceLedger Catalog Copilot!

I am your multi-agent product intelligence assistant. I have **live read & execution access** to:
- 🗄️ **SQLite Product Database**: All product records, extracted fields, and source documents.
- ⚖️ **ValidationAgent**: Cross-source conflict detection & trust tier resolution.
- 🔗 **GraphAgent**: Product variant family & relationship analysis.
- 🛡️ **DashboardService**: Quality metrics & anti-hardcoding audits.
- 📜 **ExplainabilityLayer**: Source excerpt line-level citations.

Ask me anything about your catalog, or click a quick-start chip below!`,
          cited_skus: [],
          executed_tools: [
            {
              agent: 'CopilotEngine',
              tool_name: 'initialize_agents',
              summary: 'Initialized 5 pipeline agents and grounded against live ProductStore SQLite database.',
            }
          ],
          data_preview: [],
          suggested_actions: [
            'Filter pumps by flow rate',
            'Scan cross-source field conflicts',
            'Run anti-hardcoding quality audit'
          ],
        },
      },
    ]);
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const handleSend = async (customPrompt?: string) => {
    const promptToUse = customPrompt || inputPrompt;
    if (!promptToUse.trim() || isLoading) return;

    const userMsgId = `user-${Date.now()}`;
    const copilotMsgId = `copilot-${Date.now()}`;
    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    setMessages((prev) => [
      ...prev,
      {
        id: userMsgId,
        sender: 'user',
        text: promptToUse,
        timestamp: timeStr,
      },
      {
        id: copilotMsgId,
        sender: 'copilot',
        timestamp: timeStr,
        isLoading: true,
      },
    ]);

    if (!customPrompt) setInputPrompt('');
    setIsLoading(true);

    try {
      const res = await sendCopilotMessage(promptToUse);
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === copilotMsgId ? { ...msg, isLoading: false, data: res } : msg
        )
      );
    } catch (err: any) {
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === copilotMsgId
            ? {
                ...msg,
                isLoading: false,
                data: {
                  question: promptToUse,
                  answer: `⚠️ **Query Execution Error**: ${err.message || 'Could not process query.'}`,
                  cited_skus: [],
                  executed_tools: [],
                  data_preview: [],
                  suggested_actions: ['Retry request', 'Check backend logs'],
                },
              }
            : msg
        )
      );
    } finally {
      setIsLoading(false);
    }
  };

  const toggleToolsExpand = (msgId: string) => {
    setExpandedTools((prev) => ({ ...prev, [msgId]: !prev[msgId] }));
  };

  return (
    <div className="flex flex-col h-[calc(100vh-100px)] w-full gap-4 max-w-7xl mx-auto px-4 sm:px-6 py-4">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 p-5 rounded-[24px] bg-white/70 backdrop-blur-xl border border-white/80 ring-1 ring-white/50 shadow-md">
        <div className="flex items-center gap-3.5">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-[#E8622C] to-[#191715] flex items-center justify-center text-white shadow-lg shadow-[#E8622C]/20">
            <Bot className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-xl font-black text-[#191715] flex items-center gap-2">
              Catalog Copilot & Multi-Agent Data Chat
              <span className="text-xs font-bold px-2.5 py-0.5 rounded-full bg-[#E8622C]/10 text-[#E8622C] border border-[#E8622C]/20">
                Full Agent Access
              </span>
            </h1>
            <p className="text-xs text-[#8C8276] font-medium">
              Real-time conversational catalog queries, multi-agent tool execution, and SQLite data inspection
            </p>
          </div>
        </div>

        {/* Agent Badges */}
        <div className="flex items-center flex-wrap gap-2 text-xs font-bold">
          <span className="px-2.5 py-1 rounded-xl bg-white border border-[#191715]/10 text-[#191715]/80 flex items-center gap-1.5 shadow-xs">
            <Cpu className="w-3.5 h-3.5 text-[#E8622C]" /> Ingestion & Extraction
          </span>
          <span className="px-2.5 py-1 rounded-xl bg-white border border-[#191715]/10 text-[#191715]/80 flex items-center gap-1.5 shadow-xs">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" /> ValidationAgent
          </span>
          <span className="px-2.5 py-1 rounded-xl bg-white border border-[#191715]/10 text-[#191715]/80 flex items-center gap-1.5 shadow-xs">
            <GitFork className="w-3.5 h-3.5 text-blue-600" /> GraphAgent
          </span>
          <span className="px-2.5 py-1 rounded-xl bg-white border border-[#191715]/10 text-[#191715]/80 flex items-center gap-1.5 shadow-xs">
            <Layers className="w-3.5 h-3.5 text-purple-600" /> Explainability
          </span>
        </div>
      </div>

      {/* Main Chat Window */}
      <div className="flex-1 overflow-y-auto rounded-[24px] bg-white/60 backdrop-blur-xl border border-white/80 ring-1 ring-white/50 p-6 flex flex-col gap-6 shadow-md">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex flex-col ${msg.sender === 'user' ? 'items-end' : 'items-start'} max-w-4xl ${
              msg.sender === 'user' ? 'ml-auto' : 'mr-auto'
            } w-full`}
          >
            {/* Sender Label */}
            <div className="flex items-center gap-2 mb-1.5 px-1">
              <span className="text-[11px] font-bold text-[#8C8276]">
                {msg.sender === 'user' ? 'You' : 'Catalog Copilot Agent'}
              </span>
              <span className="text-[10px] text-[#8C8276]/60">{msg.timestamp}</span>
            </div>

            {/* Bubble Content */}
            <div
              className={`rounded-[22px] p-5 shadow-sm transition-all ${
                msg.sender === 'user'
                  ? 'bg-[#191715] text-white rounded-br-xs'
                  : 'bg-white/90 border border-white text-[#191715] rounded-bl-xs'
              }`}
            >
              {msg.isLoading ? (
                <div className="flex items-center gap-3 py-2 text-sm font-semibold text-[#8C8276]">
                  <Loader2 className="w-5 h-5 animate-spin text-[#E8622C]" />
                  <span>Dispatching multi-agent tools & querying live database...</span>
                </div>
              ) : msg.sender === 'user' ? (
                <p className="text-sm font-medium whitespace-pre-wrap">{msg.text}</p>
              ) : (
                <div className="space-y-4">
                  {/* Markdown Response */}
                  <div
                    className="prose prose-sm max-w-none text-sm text-[#191715]/90 leading-relaxed font-normal"
                    dangerouslySetInnerHTML={{
                      __html: (msg.data?.answer || '')
                        .replace(/^### (.*$)/gim, '<h3 class="text-base font-black text-[#191715] mt-2 mb-1">$1</h3>')
                        .replace(/\*\*(.*?)\*\*/g, '<strong class="font-black text-[#191715]">$1</strong>')
                        .replace(/\n/g, '<br/>'),
                    }}
                  />

                  {/* Executed Agent Tools Accordion */}
                  {msg.data?.executed_tools && msg.data.executed_tools.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-[#191715]/10">
                      <button
                        onClick={() => toggleToolsExpand(msg.id)}
                        className="flex items-center justify-between w-full px-3 py-2 rounded-xl bg-[#F5E9D8]/50 hover:bg-[#F5E9D8] text-xs font-bold text-[#191715] transition-colors cursor-pointer"
                      >
                        <span className="flex items-center gap-2">
                          <Cpu className="w-4 h-4 text-[#E8622C]" />
                          Executed Pipeline Agents ({msg.data.executed_tools.length})
                        </span>
                        {expandedTools[msg.id] ? (
                          <ChevronUp className="w-4 h-4 text-[#8C8276]" />
                        ) : (
                          <ChevronDown className="w-4 h-4 text-[#8C8276]" />
                        )}
                      </button>

                      {expandedTools[msg.id] && (
                        <div className="mt-2 space-y-2 pl-2">
                          {msg.data.executed_tools.map((tool, idx) => (
                            <div
                              key={idx}
                              className="p-3 rounded-xl bg-white border border-[#191715]/10 text-xs shadow-2xs space-y-1"
                            >
                              <div className="flex items-center justify-between">
                                <span className="font-extrabold text-[#E8622C]">{tool.agent}</span>
                                <span className="font-mono text-[10px] text-[#8C8276] px-1.5 py-0.5 rounded bg-gray-100">
                                  {tool.tool_name}
                                </span>
                              </div>
                              <p className="text-[#191715]/80 font-medium">{tool.summary}</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Cited SKUs */}
                  {msg.data?.cited_skus && msg.data.cited_skus.length > 0 && (
                    <div className="flex items-center flex-wrap gap-2 pt-2">
                      <span className="text-xs font-bold text-[#8C8276] flex items-center gap-1">
                        <FileText className="w-3.5 h-3.5 text-[#E8622C]" /> Cited SKUs:
                      </span>
                      {msg.data.cited_skus.map((sku) => (
                        <button
                          key={sku}
                          onClick={() => onSelectProduct && onSelectProduct(sku)}
                          className="px-2.5 py-1 rounded-xl bg-[#E8622C]/10 hover:bg-[#E8622C] hover:text-white text-[#E8622C] text-xs font-mono font-bold transition-all cursor-pointer border border-[#E8622C]/20 shadow-2xs"
                        >
                          {sku} →
                        </button>
                      ))}
                    </div>
                  )}

                  {/* Data Preview Table */}
                  {msg.data?.data_preview && msg.data.data_preview.length > 0 && (
                    <div className="mt-3 overflow-x-auto rounded-xl border border-[#191715]/10 bg-white/80 p-3">
                      <table className="w-full text-left text-xs">
                        <thead>
                          <tr className="border-b border-[#191715]/10 font-bold text-[#191715]">
                            <th className="py-1.5 px-2">SKU</th>
                            <th className="py-1.5 px-2">Product Name</th>
                            <th className="py-1.5 px-2">Category</th>
                            <th className="py-1.5 px-2">Confidence</th>
                          </tr>
                        </thead>
                        <tbody>
                          {msg.data.data_preview.map((p, idx) => (
                            <tr key={idx} className="border-b border-[#191715]/5 hover:bg-[#F5E9D8]/30">
                              <td className="py-1.5 px-2 font-mono font-bold text-[#E8622C]">{p.sku}</td>
                              <td className="py-1.5 px-2 font-medium text-[#191715]">{p.name}</td>
                              <td className="py-1.5 px-2 text-[#8C8276]">{p.category}</td>
                              <td className="py-1.5 px-2 font-bold">{p.confidence_overall}%</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {/* Suggested Follow-up Actions */}
                  {msg.data?.suggested_actions && msg.data.suggested_actions.length > 0 && (
                    <div className="pt-2 flex items-center flex-wrap gap-2">
                      {msg.data.suggested_actions.map((act, idx) => (
                        <button
                          key={idx}
                          onClick={() => handleSend(act)}
                          className="px-3 py-1.5 rounded-xl bg-white border border-[#191715]/15 hover:border-[#E8622C] text-[#191715] hover:text-[#E8622C] text-xs font-bold transition-all cursor-pointer flex items-center gap-1.5 shadow-2xs"
                        >
                          <Sparkles className="w-3.5 h-3.5 text-[#E8622C]" />
                          {act}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={chatEndRef} />
      </div>

      {/* Quick-Start Prompt Suggestions */}
      {suggestions.length > 0 && (
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          {suggestions.map((sug, idx) => (
            <button
              key={idx}
              onClick={() => handleSend(sug.prompt)}
              className="px-3.5 py-2 rounded-2xl bg-white/80 hover:bg-white border border-white ring-1 ring-white/60 text-xs font-bold text-[#191715] hover:text-[#E8622C] transition-all whitespace-nowrap shadow-xs cursor-pointer flex items-center gap-2"
            >
              <span>{sug.label}</span>
            </button>
          ))}
        </div>
      )}

      {/* Input Control Bar */}
      <div className="relative flex items-center w-full">
        <textarea
          rows={1}
          value={inputPrompt}
          onChange={(e) => setInputPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder="Ask Copilot about catalog SKUs, cross-source conflicts, quality audits, or variant families... (Press Enter to send)"
          className="w-full pl-5 pr-14 py-4 rounded-[24px] bg-white/90 backdrop-blur-xl border border-white/90 ring-1 ring-white/60 text-sm text-[#191715] placeholder-[#8C8276] font-medium shadow-md focus:outline-none focus:ring-2 focus:ring-[#E8622C]/50 resize-none"
        />
        <button
          onClick={() => handleSend()}
          disabled={!inputPrompt.trim() || isLoading}
          className="absolute right-3 p-3 rounded-2xl bg-[#E8622C] hover:bg-[#D45320] text-white disabled:opacity-50 transition-all cursor-pointer shadow-lg shadow-[#E8622C]/30"
        >
          {isLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
        </button>
      </div>
    </div>
  );
};
