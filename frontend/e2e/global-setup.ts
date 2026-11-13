// The e2e tests expect the invented sample city. Locally Playwright reuses an
// app that is already running on port 8000: if that one serves another network
// (e.g. WHATIF_DATABASE=gdansk.db ./dev.sh), stop early with a clear message
// instead of twenty timeouts.

const API = 'http://localhost:8000'

export default async function globalSetup(): Promise<void> {
  const response = await fetch(`${API}/api/network`)
  const network = (await response.json()) as { source?: { name: string } | null }
  if (network.source) {
    throw new Error(
      `The backend on port 8000 serves "${network.source.name}", but the e2e tests need the sample city. ` +
        'Stop that app (or restart it without WHATIF_DATABASE) and run the tests again.',
    )
  }
}
