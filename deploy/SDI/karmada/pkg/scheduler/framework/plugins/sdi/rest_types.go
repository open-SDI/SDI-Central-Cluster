package sdi

// GetALEWeightRequest - ALE 가중치 요청 구조체
type GetALEWeightRequest struct {
	DeviceId  string   `json:"device_id"`
	DeviceIds []string `json:"device_ids"`
}

// GetALEWeightResponse - ALE 가중치 응답 구조체
type GetALEWeightResponse struct {
	Success       bool        `json:"success"`
	Message       string      `json:"message"`
	TotalDevices  int32       `json:"total_devices"`
	AleScores     []*ALEScore `json:"ale_scores"`
	FailedDevices []string    `json:"failed_devices"`
}

// ALEScore - ALE 점수 구조체
type ALEScore struct {
	DeviceId             string  `json:"device_id"`
	AccuracyScore        float64 `json:"accuracy_score"`
	LatencyScore         float64 `json:"latency_score"`
	EnergyScore          float64 `json:"energy_score"`
	CalculationTimestamp string  `json:"calculation_timestamp"`
}



