import { Play, TriangleAlert } from 'lucide-react'

import { Button } from './ui/Button'

interface RunBarProps {
  changeCount: number
  running: boolean
  error: string | null
  onRun: () => void
}

/** Pinned to the bottom of the panel: the one primary action. */
export function RunBar({ changeCount, running, error, onRun }: RunBarProps) {
  return (
    <div className="space-y-2">
      {error && (
        <p role="alert" className="flex gap-2 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-800">
          <TriangleAlert size={16} className="mt-0.5 shrink-0" aria-hidden />
          {error}
        </p>
      )}
      <Button
        variant="primary"
        size="lg"
        icon={Play}
        loading={running}
        disabled={changeCount === 0}
        onClick={onRun}
        className="w-full"
      >
        {running
          ? 'Simulating…'
          : changeCount === 0
            ? 'Add a change to simulate'
            : `Run simulation (${changeCount} ${changeCount === 1 ? 'change' : 'changes'})`}
      </Button>
    </div>
  )
}
