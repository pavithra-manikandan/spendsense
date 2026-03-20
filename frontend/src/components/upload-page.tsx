import { useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Upload, FileText, CheckCircle, AlertCircle, ArrowRight } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { ingestCSV } from "@/lib/api";

const CAT_EMOJI: Record<string, string> = {
  food: "🍔", groceries: "🥬", shopping: "🛍️", transport: "🚗",
  subscriptions: "📱", health: "💊", entertainment: "🎬", utilities: "💡", other: "📦",
};

interface UploadResult {
  imported: number;
  duplicates_skipped: number;
  total_in_system: number;
  sample: { merchant: string; merchant_raw: string; amount: number; category: string }[];
  error?: string;
}

export function UploadPage({ onNavigate }: { onNavigate: (view: string) => void }) {
  const [dragOver, setDragOver] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleUpload = async (file: File) => {
    if (!file.name.endsWith(".csv")) {
      setError("Please upload a .csv file");
      return;
    }
    setIsUploading(true);
    setResult(null);
    setError(null);
    try {
      const data = await ingestCSV(file);
      if (data.detail) {
        setError(typeof data.detail === "string" ? data.detail : data.detail.message || "Upload failed");
      } else {
        setResult(data);
      }
    } catch {
      setError("Couldn't reach the server. Is it running on port 8000?");
    }
    setIsUploading(false);
  };

  return (
    <div className="max-w-xl mx-auto py-8">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
        {/* Drop zone */}
        <div
          onDragOver={e => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={e => { e.preventDefault(); setDragOver(false); handleUpload(e.dataTransfer.files[0]); }}
          onClick={() => fileRef.current?.click()}
          className={`border-2 border-dashed rounded-2xl p-16 text-center cursor-pointer transition-all ${
            dragOver ? "border-primary bg-primary/5" : "border-border hover:border-primary/40 bg-card"
          }`}
        >
          <input ref={fileRef} type="file" accept=".csv" className="hidden"
            onChange={e => e.target.files?.[0] && handleUpload(e.target.files[0])} />

          <motion.div animate={isUploading ? { rotate: 360 } : {}} transition={isUploading ? { repeat: Infinity, duration: 1.5, ease: "linear" } : {}}>
            {isUploading ? <FileText className="w-12 h-12 text-primary mx-auto mb-4" />
              : <Upload className="w-12 h-12 text-muted-foreground mx-auto mb-4" />}
          </motion.div>

          <h3 className="text-lg font-medium mb-2">
            {isUploading ? "Processing your statement..." : "Drop your bank CSV here"}
          </h3>
          <p className="text-sm text-muted-foreground">
            or click to browse — works with Chase, Amex, Capital One, any bank
          </p>
        </div>

        {/* Error */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="mt-4"
            >
              <Card className="border-destructive/50 bg-destructive/10">
                <CardContent className="pt-4 flex items-center gap-3">
                  <AlertCircle className="w-5 h-5 text-destructive shrink-0" />
                  <p className="text-sm text-destructive">{error}</p>
                </CardContent>
              </Card>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Success */}
        <AnimatePresence>
          {result && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-6 space-y-4"
            >
              <Card className="border-chart-2/30 bg-chart-2/5">
                <CardContent className="pt-5">
                  <div className="flex items-center gap-3 mb-3">
                    <CheckCircle className="w-6 h-6 text-chart-2" />
                    <div>
                      <div className="text-lg font-semibold text-chart-2">
                        Imported {result.imported} transactions
                      </div>
                      {result.duplicates_skipped > 0 && (
                        <div className="text-xs text-muted-foreground">{result.duplicates_skipped} duplicates skipped</div>
                      )}
                    </div>
                  </div>

                  <div className="flex gap-2 mt-4">
                    <button
                      onClick={() => onNavigate("dashboard")}
                      className="flex items-center gap-2 px-4 py-2 bg-chart-2 text-background rounded-lg font-medium text-sm hover:opacity-90 transition-opacity"
                    >
                      View Dashboard <ArrowRight className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => onNavigate("chat")}
                      className="flex items-center gap-2 px-4 py-2 bg-white/10 text-foreground rounded-lg font-medium text-sm hover:bg-white/15 transition-colors"
                    >
                      Ask a question
                    </button>
                  </div>
                </CardContent>
              </Card>

              {/* Normalization preview */}
              {result.sample && result.sample.length > 0 && (
                <Card className="bg-card border-border">
                  <CardContent className="pt-5">
                    <div className="text-xs text-muted-foreground mb-3 font-medium uppercase tracking-wide">Merchant normalization preview</div>
                    {result.sample.map((t, i) => (
                      <motion.div
                        key={i}
                        className="flex items-center justify-between py-2.5 border-b border-border last:border-0 text-sm"
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: i * 0.1 }}
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <span className="text-lg">{CAT_EMOJI[t.category] || "📦"}</span>
                          <div className="min-w-0">
                            <span className="text-muted-foreground line-through text-xs block truncate">{t.merchant_raw}</span>
                            <span className="font-medium block">{t.merchant}</span>
                          </div>
                        </div>
                        <span className="text-primary font-semibold ml-4">${t.amount}</span>
                      </motion.div>
                    ))}
                  </CardContent>
                </Card>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  );
}
