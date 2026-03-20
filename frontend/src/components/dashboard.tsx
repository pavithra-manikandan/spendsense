import { useEffect, useState } from "react";
import { LabelList, Pie, PieChart, BarChart, Bar, XAxis, YAxis, Tooltip, LineChart, Line, CartesianGrid } from "recharts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { type ChartConfig, ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { Badge } from "@/components/ui/badge";
import { TrendingUp, TrendingDown, DollarSign, Repeat, Zap } from "lucide-react";
import { motion } from "framer-motion";
import { getAnalysis } from "@/lib/api";

const CAT_COLORS: Record<string, string> = {
  food: "#f59e42", groceries: "#c9ea9e", shopping: "#a78bfa", transport: "#38bdf8",
  subscriptions: "#f06060", health: "#f472b6", entertainment: "#67e8f9",
  utilities: "#3a121c", other: "#686f76", housing: "#38bdf8", savings: "#56f4a8", transfers: "#e6fdbd",
};

const CAT_EMOJI: Record<string, string> = {
  food: "🍔", groceries: "🥬", shopping: "🛍️", transport: "🚗",
  subscriptions: "📱", health: "💊", entertainment: "🎬", utilities: "💡", other: "📦",
  housing: "🏠", savings: "💰",
};

interface Analysis {
  total_spent: number;
  transaction_count: number;
  date_range: string;
  daily_average: number;
  monthly_average?: number;
  by_category: Record<string, number>;
  category_percentages: Record<string, number>;
  top_merchants: { merchant: string; total: number; count: number }[];
  monthly_trend: Record<string, number>;
  anomalies: { merchant: string; amount: number; reason: string; z_score: number }[];
  recurring: { merchant: string; avg_amount: number; occurrences: number; months_seen: number; estimated_annual: number }[];
  forecast_next_month: number | null;
}

export function Dashboard({ onNavigate }: { onNavigate: (view: string) => void }) {
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchAnalysis = () => {
    setLoading(true);
    getAnalysis().then(data => {
      if (!data.error) setAnalysis(data);
      setLoading(false);
    }).catch(() => setLoading(false));
  };

  useEffect(() => {
    fetchAnalysis();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: "linear" }}>
          <Zap className="w-8 h-8 text-primary" />
        </motion.div>
      </div>
    );
  }

  if (!analysis || !analysis.transaction_count) {
    return (
      <div className="text-center py-24">
        <div className="text-6xl mb-4">🕸️</div>
        <h2 className="text-xl font-medium mb-2">No data yet</h2>
        <p className="text-muted-foreground mb-6">Upload a bank CSV or PDF to activate your spendsense</p>
        <button
          onClick={() => onNavigate("upload")}
          className="px-6 py-3 bg-primary text-primary-foreground rounded-lg font-semibold hover:opacity-90 transition-opacity"
        >
          Upload Statement
        </button>
      </div>
    );
  }

  const pieData = Object.entries(analysis.by_category).map(([name, value]) => ({
    category: name, spent: value, fill: `var(--color-${name})`,
  }));

  const pieConfig: ChartConfig = Object.fromEntries(
    Object.entries(analysis.by_category).map(([cat]) => [
      cat, { label: `${CAT_EMOJI[cat] || "📦"} ${cat.charAt(0).toUpperCase() + cat.slice(1)}`, color: CAT_COLORS[cat] || "#6b7a85" }
    ])
  );
  pieConfig.spent = { label: "Spent" };

  const barData = analysis.top_merchants.slice(0, 8).map(m => ({
    merchant: m.merchant.length > 14 ? m.merchant.slice(0, 14) + "…" : m.merchant,
    amount: m.total,
    count: m.count,
  }));

  const trendData = Object.entries(analysis.monthly_trend).map(([month, total]) => ({
    month: month.slice(5), total,
  }));

  return (
    <div className="space-y-6">
      {/* Ask AI banner */}
      <motion.div
        className="bg-primary/10 border border-primary/20 rounded-xl p-5 flex items-center justify-between"
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div>
          <div className="text-sm font-semibold text-primary">Your data is ready</div>
          <div className="text-xs text-muted-foreground mt-1">
            {analysis.transaction_count} transactions · ${analysis.total_spent.toLocaleString()} total · {analysis.date_range}
          </div>
        </div>
        <button
          onClick={() => onNavigate("chat")}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-semibold hover:opacity-90 transition-opacity flex items-center gap-2"
        >
          💬 Ask AI about my spending
        </button>
      </motion.div>

      {/* Stat cards */}
      <motion.div
        className="grid grid-cols-2 lg:grid-cols-4 gap-4"
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ duration: 0.5 }}
      >
        <StatCard icon={<DollarSign className="w-4 h-4" />} label="Monthly average" value={`$${(analysis.monthly_average || analysis.total_spent).toLocaleString()}`} color="text-destructive" />        <StatCard icon={<Zap className="w-4 h-4" />} label="Transactions" value={String(analysis.transaction_count)} color="text-chart-4" />
        <StatCard icon={<TrendingDown className="w-4 h-4" />} label="Daily average" value={`$${analysis.daily_average.toFixed(2)}`} color="text-primary" />
        <StatCard icon={<TrendingUp className="w-4 h-4" />} label="Forecast next month" value={analysis.forecast_next_month ? `$${analysis.forecast_next_month.toLocaleString()}` : "—"} color="text-chart-2" />
      </motion.div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <motion.div initial={{ opacity: 0, x: -20 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ duration: 0.5, delay: 0.1 }}>
          <Card className="bg-card border-border">
            <CardHeader className="items-center pb-0">
              <CardTitle className="text-base">
                Spending by category
                <Badge variant="outline" className="text-primary bg-primary/10 border-none ml-2 text-xs">
                  {Object.keys(analysis.by_category).length} categories
                </Badge>
              </CardTitle>
              <CardDescription>{analysis.date_range}</CardDescription>
            </CardHeader>
            <CardContent className="flex-1 pb-4">
              <ChartContainer config={pieConfig} className="[&_.recharts-text]:fill-background mx-auto aspect-square max-h-[280px]">
                <PieChart>
                  <ChartTooltip content={<ChartTooltipContent nameKey="category" hideLabel />} />
                  <Pie data={pieData} innerRadius={35} dataKey="spent" nameKey="category" cornerRadius={6} paddingAngle={3}>
                    <LabelList dataKey="spent" stroke="none" fontSize={11} fontWeight={500} fill="currentColor"
                      formatter={(value: number) => `$${value >= 1000 ? (value / 1000).toFixed(1) + 'k' : value}`} />
                  </Pie>
                </PieChart>
              </ChartContainer>
              <div className="flex flex-wrap gap-2 justify-center mt-2">
                {pieData.map(d => (
                  <span key={d.category} className="text-xs text-muted-foreground flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-sm inline-block" style={{ background: CAT_COLORS[d.category] || "#6b7a85" }} />
                    {d.category} ({analysis.category_percentages[d.category]}%)
                  </span>
                ))}
              </div>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div initial={{ opacity: 0, x: 20 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ duration: 0.5, delay: 0.2 }}>
          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="text-base">Top merchants</CardTitle>
              <CardDescription>Where your money goes</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="h-[280px]">
                <BarChartComponent data={barData} />
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>

      {/* Monthly trend */}
      {trendData.length > 1 && (
        <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.5, delay: 0.3 }}>
          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="text-base">Monthly trend</CardTitle>
              {analysis.forecast_next_month && (
                <CardDescription>
                  Forecast: <span className="text-primary font-semibold">${analysis.forecast_next_month.toLocaleString()}</span> next month
                </CardDescription>
              )}
            </CardHeader>
            <CardContent>
              <div className="h-[200px]">
                <TrendChartComponent data={trendData} />
              </div>
            </CardContent>
          </Card>
        </motion.div>
      )}

      {/* Anomalies + Recurring */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {analysis.anomalies?.length > 0 && (
          <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.5, delay: 0.1 }}>
            <Card className="bg-card border-border">
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <span>🕷️</span> Spendsense alerts
                  <Badge variant="outline" className="text-destructive bg-destructive/10 border-none text-xs">
                    {analysis.anomalies.length} found
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {analysis.anomalies.slice(0, 5).map((a, i) => (
                  <motion.div
                    key={i}
                    className="flex justify-between items-start py-2 border-b border-border last:border-0"
                    initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }}
                  >
                    <div>
                      <div className="text-sm font-medium">{a.merchant}</div>
                      <div className="text-xs text-muted-foreground mt-0.5">{a.reason}</div>
                    </div>
                    <div className="text-sm font-semibold text-destructive">${a.amount}</div>
                  </motion.div>
                ))}
              </CardContent>
            </Card>
          </motion.div>
        )}

        {analysis.recurring?.length > 0 && (
          <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.5, delay: 0.2 }}>
            <Card className="bg-card border-border">
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <Repeat className="w-4 h-4 text-chart-3" /> Recurring charges
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {analysis.recurring.slice(0, 5).map((r, i) => (
                  <motion.div
                    key={i}
                    className="flex justify-between items-center py-2 border-b border-border last:border-0"
                    initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }}
                  >
                    <div>
                      <div className="text-sm font-medium">{r.merchant}</div>
                      <div className="text-xs text-muted-foreground">{r.occurrences}x over {r.months_seen} months</div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-semibold text-primary">${r.avg_amount}/mo</div>
                      <div className="text-xs text-muted-foreground">${r.estimated_annual}/yr</div>
                    </div>
                  </motion.div>
                ))}
              </CardContent>
            </Card>
          </motion.div>
        )}
      </div>
    </div>
  );
}

function StatCard({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: string; color: string }) {
  return (
    <Card className="bg-card border-border">
      <CardContent className="pt-5 pb-4">
        <div className="flex items-center gap-2 text-muted-foreground mb-2">
          {icon}
          <span className="text-xs">{label}</span>
        </div>
        <div className={`text-2xl font-bold tracking-tight ${color}`}>{value}</div>
      </CardContent>
    </Card>
  );
}

function BarChartComponent({ data }: { data: { merchant: string; amount: number; count: number }[] }) {
  return (
    <BarChart data={data} layout="vertical" width={450} height={280} margin={{ left: 5, right: 20 }}>
      <XAxis type="number" tick={{ fill: "#6b7a85", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={v => `$${v}`} />
      <YAxis type="category" dataKey="merchant" tick={{ fill: "#6b7a85", fontSize: 11 }} axisLine={false} tickLine={false} width={100} />
      <Tooltip
        content={({ payload }) => payload?.[0] ? (
          <div className="bg-background border border-border rounded-lg px-3 py-2 text-xs shadow-xl">
            <div className="font-semibold text-primary">${payload[0].value?.toLocaleString()}</div>
            <div className="text-muted-foreground">{payload[0].payload.count} transactions</div>
          </div>
        ) : null}
      />
      <Bar dataKey="amount" fill="var(--color-chart-1)" radius={[0, 4, 4, 0]} barSize={18} />
    </BarChart>
  );
}

function TrendChartComponent({ data }: { data: { month: string; total: number }[] }) {
  return (
    <LineChart data={data} width={900} height={200} margin={{ left: 10, right: 20, top: 10 }}>
      <CartesianGrid strokeDasharray="3 3" stroke="#1e2830" />
      <XAxis dataKey="month" tick={{ fill: "#6b7a85", fontSize: 11 }} axisLine={false} />
      <YAxis tick={{ fill: "#6b7a85", fontSize: 11 }} axisLine={false} tickFormatter={v => `$${v}`} />
      <Tooltip
        content={({ payload, label }) => payload?.[0] ? (
          <div className="bg-background border border-border rounded-lg px-3 py-2 text-xs shadow-xl">
            <div className="text-muted-foreground">{label}</div>
            <div className="font-semibold text-chart-2">${payload[0].value?.toLocaleString()}</div>
          </div>
        ) : null}
      />
      <Line type="monotone" dataKey="total" stroke="var(--color-chart-2)" strokeWidth={2.5} dot={{ fill: "var(--color-chart-2)", r: 4 }} />
    </LineChart>
  );
}