package sdi

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"
)

// REST API 응답 구조체
type ScoresResponse struct {
	Success       bool   `json:"success"`
	AccuracyScore int    `json:"accuracy_score"`
	LatencyScore  int    `json:"latency_score"`
	EnergyScore   int    `json:"energy_score"`
	Timestamp     string `json:"timestamp"`
	Message       string `json:"message,omitempty"`
}

// ALE Weights REST API 응답 구조체
type ALEWeightsResponse struct {
	Success        bool                   `json:"success"`
	Message        string                 `json:"message"`
	TotalDevices   int                    `json:"total_devices"`
	ALEScores      []ALEScoreData         `json:"ale_scores"`
	FailedDevices  []string               `json:"failed_devices"`
}

type ALEScoreData struct {
	DeviceID              string  `json:"device_id"`
	AccuracyScore         float64 `json:"accuracy_score"`
	LatencyScore          float64 `json:"latency_score"`
	EnergyScore           float64 `json:"energy_score"`
	CalculationTimestamp  string  `json:"calculation_timestamp"`
}

// 가능한 서비스 주소들을 시도하는 함수
func tryConnectToAnalysisEngine(ctx context.Context) (string, error) {
	// 환경변수에서 서비스 주소를 가져오거나 기본값 사용
	addr := os.Getenv("ANALYSIS_ENGINE_ADDR")
	if addr != "" {
		// 환경변수로 지정된 주소 시도
		if err := tryConnect(ctx, addr); err == nil {
			return addr, nil
		}
		fmt.Printf("[SDI] 환경변수 주소 %s 연결 실패\n", addr)
	}

	// 가능한 서비스 주소들을 순차적으로 시도
	possibleAddresses := []string{
		"http://analysis-engine-service.default.svc.cluster.local:5000",
		"http://analysis-engine.default.svc.cluster.local:5000",
		"http://analysis-engine-service.sdi-system.svc.cluster.local:5000",
		"http://analysis-engine.sdi-system.svc.cluster.local:5000",
		"http://localhost:5000", // 로컬 테스트용
	}

	for _, addr := range possibleAddresses {
		fmt.Printf("[SDI] %s 연결 시도 중...\n", addr)
		if err := tryConnect(ctx, addr); err == nil {
			fmt.Printf("[SDI] %s 연결 성공!\n", addr)
			return addr, nil
		}
		fmt.Printf("[SDI] %s 연결 실패\n", addr)
	}

	return "", fmt.Errorf("모든 가능한 주소에서 연결 실패")
}

func tryConnect(ctx context.Context, addr string) error {
	client := &http.Client{
		Timeout: 5 * time.Second,
	}

	req, err := http.NewRequestWithContext(ctx, "GET", addr+"/health", nil)
	if err != nil {
		return err
	}

	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("HTTP %d", resp.StatusCode)
	}

	return nil
}

func fetchScoresFromAnalysisEngine(ctx context.Context) (*ScoreValues, error) {
	addr, err := tryConnectToAnalysisEngine(ctx)
	if err != nil {
		return nil, fmt.Errorf("analysis-engine 연결 실패: %w", err)
	}

	fmt.Printf("[SDI] %s에 연결됨\n", addr)

	client := &http.Client{
		Timeout: 8 * time.Second,
	}

	// REST API 호출
	req, err := http.NewRequestWithContext(ctx, "GET", addr+"/api/scores", nil)
	if err != nil {
		return nil, fmt.Errorf("요청 생성 실패: %w", err)
	}

	fmt.Printf("[SDI] REST API 호출 중...\n")
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("REST API 호출 실패: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(body))
	}

	// 응답 파싱
	var scoresResp ScoresResponse
	if err := json.NewDecoder(resp.Body).Decode(&scoresResp); err != nil {
		return nil, fmt.Errorf("응답 파싱 실패: %w", err)
	}

	fmt.Printf("[SDI] REST API 응답 받음: %+v\n", scoresResp)

	if !scoresResp.Success {
		return nil, fmt.Errorf("API 응답 실패: %s", scoresResp.Message)
	}

	return &ScoreValues{
		Accuracy: scoresResp.AccuracyScore,
		Latency:  scoresResp.LatencyScore,
		Energy:   scoresResp.EnergyScore,
	}, nil
}

func fetchALEWeightsFromAnalysisEngine(ctx context.Context, deviceID string, deviceIDs []string) (*GetALEWeightResponse, error) {
	addr, err := tryConnectToAnalysisEngine(ctx)
	if err != nil {
		return nil, fmt.Errorf("analysis-engine 연결 실패: %w", err)
	}

	fmt.Printf("[SDI] %s에 연결됨\n", addr)

	client := &http.Client{
		Timeout: 8 * time.Second,
	}

	// REST API 호출
	req, err := http.NewRequestWithContext(ctx, "GET", addr+"/api/ale-weights", nil)
	if err != nil {
		return nil, fmt.Errorf("요청 생성 실패: %w", err)
	}

	// 쿼리 파라미터 추가
	q := req.URL.Query()
	if deviceID != "" {
		q.Add("device_id", deviceID)
	}
	for _, id := range deviceIDs {
		q.Add("device_ids", id)
	}
	req.URL.RawQuery = q.Encode()

	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("REST API 호출 실패: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(body))
	}

	// 응답 파싱
	var aleResp ALEWeightsResponse
	if err := json.NewDecoder(resp.Body).Decode(&aleResp); err != nil {
		return nil, fmt.Errorf("응답 파싱 실패: %w", err)
	}

	// proto 구조체로 변환
	aleScores := make([]*ALEScore, 0, len(aleResp.ALEScores))
	for _, score := range aleResp.ALEScores {
		aleScores = append(aleScores, &ALEScore{
			DeviceId:             score.DeviceID,
			AccuracyScore:        score.AccuracyScore,
			LatencyScore:         score.LatencyScore,
			EnergyScore:          score.EnergyScore,
			CalculationTimestamp: score.CalculationTimestamp,
		})
	}

	return &GetALEWeightResponse{
		Success:       aleResp.Success,
		Message:       aleResp.Message,
		TotalDevices:  int32(aleResp.TotalDevices),
		AleScores:     aleScores,
		FailedDevices: aleResp.FailedDevices,
	}, nil
}
