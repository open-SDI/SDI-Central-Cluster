package sdi

import (
	"context"
)

// fetchScores is the indirection point used by the scheduler to obtain A/L/E.
// Now uses REST API instead of gRPC
func fetchScores(ctx context.Context) (*ScoreValues, error) {
	return fetchScoresFromAnalysisEngine(ctx)
}
