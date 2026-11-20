import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Diff, ScoreBar } from './components'

describe('ScoreBar', () => {
  it('marks a score at or above the threshold', () => {
    render(<ScoreBar score={0.96} threshold={0.8} />)
    expect(screen.getByText('0.960')).toBeInTheDocument()
    expect(screen.getByText('above threshold')).toBeInTheDocument()
  })
  it('marks a score below the threshold', () => {
    render(<ScoreBar score={0.24} threshold={0.8} />)
    expect(screen.getByText('below threshold')).toBeInTheDocument()
  })
})

describe('Diff', () => {
  const cell = (v: number) => {
    render(<table><tbody><tr><Diff value={v} /></tr></tbody></table>)
    return screen.getByRole('cell')
  }
  it('highlights a non-zero difference', () => expect(cell(-198.94)).toHaveClass('diff'))
  it('does not highlight zero', () => expect(cell(0)).not.toHaveClass('diff'))
})
