import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { BarChart3, MessageSquare, Upload, List } from "lucide-react";
import { cn } from "@/lib/utils";
import { Dashboard } from "@/components/dashboard";
import { SpendSenseChat } from "@/components/spendsense-chat";
import { UploadPage } from "@/components/upload-page";
import { getTransactions } from "@/lib/api";

const CAT_EMOJI: Record<string, string> = {
  food: "🍔", groceries: "🥬", shopping: "🛍️", transport: "🚗",
  subscriptions: "📱", health: "💊", entertainment: "🎬", utilities: "💡", other: "📦",
  housing: "🏠", savings: "💰",
};

type View = "landing" | "dashboard" | "chat" | "upload" | "transactions";

const NAV_ITEMS: { id: View; label: string; icon: React.ReactNode }[] = [
  { id: "dashboard", label: "Dashboard", icon: <BarChart3 className="w-4 h-4" /> },
  { id: "chat", label: "Ask", icon: <MessageSquare className="w-4 h-4" /> },
  { id: "upload", label: "Upload", icon: <Upload className="w-4 h-4" /> },
  { id: "transactions", label: "History", icon: <List className="w-4 h-4" /> },
];

interface Transaction {
  id: string;
  merchant: string;
  amount: number;
  date: string;
  category: string;
  source: string;
}

export default function App() {
  const [view, setView] = useState<View>("landing");
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const hasData = transactions.length > 0;

  useEffect(() => {
    getTransactions().then(data => {
      if (Array.isArray(data) && data.length > 0) {
        setTransactions(data);
        setView("dashboard");
      }
    }).catch(() => {});
  }, []);

  const refreshTransactions = () => {
    getTransactions().then(data => {
      if (Array.isArray(data)) setTransactions(data);
    }).catch(() => {});
  };

  const handleNavigate = (v: string) => {
    setView(v as View);
    if (v === "dashboard" || v === "chat") refreshTransactions();
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap" rel="stylesheet" />

      {view === "landing" && (
        <LandingPage onNavigate={handleNavigate} />
      )}

      {view !== "landing" && (
        <>
          <header className="sticky top-0 z-50 backdrop-blur-xl bg-background/80 border-b border-border">
            <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
              <div className="flex items-center gap-3 cursor-pointer" onClick={() => setView(hasData ? "dashboard" : "landing")}>
                <span className="text-2xl">💸</span>
                <div>
                  <div className="text-base font-semibold tracking-tight leading-none">spendsense</div>
                  <div className="text-[10px] text-muted-foreground font-light">spidey sense, but for your money</div>
                </div>
              </div>
              <nav className="flex items-center gap-1 bg-secondary/50 rounded-lg p-1">
                {NAV_ITEMS.map(item => (
                  <button
                    key={item.id}
                    onClick={() => handleNavigate(item.id)}
                    className={cn(
                      "flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all",
                      view === item.id
                        ? "bg-background text-primary shadow-sm border border-border"
                        : "text-muted-foreground hover:text-foreground"
                    )}
                  >
                    {item.icon}
                    <span className="hidden sm:inline">{item.label}</span>
                  </button>
                ))}
              </nav>
            </div>
          </header>

          <main className={cn(
            "max-w-6xl mx-auto",
            view === "chat" ? "h-[calc(100vh-3.5rem)]" : "px-6 py-6"
          )}>
            {view === "dashboard" && <Dashboard onNavigate={handleNavigate} />}
            {view === "chat" && <SpendSenseChat hasData={hasData} />}
            {view === "upload" && <UploadPage onNavigate={handleNavigate} />}
            {view === "transactions" && <TransactionList transactions={transactions} />}
          </main>
        </>
      )}
    </div>
  );
}

function LandingPage({ onNavigate }: { onNavigate: (view: string) => void }) {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center overflow-hidden relative">
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-[500px] h-[500px] bg-primary/8 rounded-full filter blur-[150px] animate-pulse" />
        <div className="absolute bottom-1/4 right-1/4 w-[400px] h-[400px] bg-chart-2/8 rounded-full filter blur-[130px] animate-pulse" style={{ animationDelay: "1s" }} />
        <div className="absolute top-1/3 right-1/3 w-[300px] h-[300px] bg-chart-3/5 rounded-full filter blur-[100px] animate-pulse" style={{ animationDelay: "2s" }} />
      </div>

      <motion.div
        className="relative z-10 text-center"
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease: "easeOut" }}
      >
        <motion.div className="text-7xl mb-6" initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ delay: 0.2, duration: 0.5 }}>
          💸
        </motion.div>

        <motion.h1
          className="text-6xl md:text-8xl font-bold tracking-tighter bg-clip-text text-transparent bg-gradient-to-b from-white via-white/90 to-white/30"
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3, duration: 0.6 }}
        >
          spendsense
        </motion.h1>

        <motion.p className="text-lg text-muted-foreground mt-4 font-light" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }}>
          spidey sense, but for your money
        </motion.p>

        <motion.p className="text-sm text-muted-foreground/60 mt-2 max-w-md mx-auto" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.7 }}>
          Upload your bank statement. Ask where your money goes. Get specific, actionable answers.
        </motion.p>

        <motion.button
          className="mt-12 px-8 py-3 bg-primary text-primary-foreground rounded-xl text-sm font-semibold hover:opacity-90 transition-opacity"
          initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.9 }}
          whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
          onClick={() => onNavigate("upload")}
        >
          Click here to get started
        </motion.button>
      </motion.div>
    </div>
  );
}

function TransactionList({ transactions }: { transactions: Transaction[] }) {
  if (!transactions.length) {
    return (
      <div className="text-center py-24 text-muted-foreground">
        <div className="text-4xl mb-3">📋</div>
        <p>No transactions yet. Upload a CSV or PDF to get started.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="text-sm text-muted-foreground mb-4">{transactions.length} transactions</div>
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        {transactions.slice(0, 100).map((t, i) => (
          <motion.div
            key={t.id || i}
            className="flex items-center justify-between px-4 py-3 border-b border-border last:border-0 hover:bg-secondary/30 transition-colors"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: Math.min(i * 0.02, 0.5) }}
          >
            <div className="flex items-center gap-3 min-w-0">
              <span className="text-xl w-8 text-center">{CAT_EMOJI[t.category] || "📦"}</span>
              <div className="min-w-0">
                <div className="text-sm font-medium truncate">{t.merchant}</div>
                <div className="text-xs text-muted-foreground flex items-center gap-2">
                  <span>{t.category}</span>
                  <span>·</span>
                  <span>{t.date}</span>
                  {t.source !== "manual" && (
                    <span className="px-1.5 py-0.5 rounded text-[10px] bg-primary/10 text-primary">{t.source}</span>
                  )}
                </div>
              </div>
            </div>
            <div className="text-sm font-semibold tabular-nums ml-4">${t.amount?.toFixed(2)}</div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}