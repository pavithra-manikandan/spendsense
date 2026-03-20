const API = "/api";

export async function ingestCSV(file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API}/ingest/csv`, { method: "POST", body: form });
  return res.json();
}

export async function ingestManual(merchant: string, amount: number, category: string, date?: string) {
  const res = await fetch(`${API}/ingest/manual`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ merchant, amount, category, date }),
  });
  return res.json();
}

export async function askAgent(question: string) {
  const res = await fetch(`${API}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  return res.json();
}

export async function getAnalysis() {
  const res = await fetch(`${API}/analysis`);
  return res.json();
}

export async function getTransactions(category?: string) {
  const params = category ? `?category=${category}` : "";
  const res = await fetch(`${API}/transactions${params}`);
  return res.json();
}

export async function getHealth() {
  const res = await fetch(`${API}/`);
  return res.json();
}
