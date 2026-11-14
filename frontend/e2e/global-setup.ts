// The e2e tests run on the invented sample city (test data). Locally Playwright
// reuses an app that is already running on port 8000: if that is the real app
// (./dev.sh, serving Gdańsk), stop early with a clear message instead of twenty
// timeouts.

const API = 'http://localhost:8000'

export default async function globalSetup(): Promise<void> {
  const response = await fetch(`${API}/api/network`)
  const network = (await response.json()) as { source?: { name: string } | null }
  if (network.source) {
    throw new Error(
      `The backend on port 8000 serves "${network.source.name}", but the e2e tests need the sample city. ` +
        'Stop the app (./dev.sh) and run the tests again: they start their own servers on a test database.',
    )
  }
}
