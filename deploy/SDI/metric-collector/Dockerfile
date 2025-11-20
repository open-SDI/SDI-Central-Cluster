FROM golang:1.24-alpine AS builder
WORKDIR /src

COPY go.mod ./
RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -o metric-collector ./cmd/metric-collector

FROM gcr.io/distroless/static-debian11
WORKDIR /app
COPY --from=builder /src/metric-collector .
USER nonroot:nonroot
ENTRYPOINT ["/app/metric-collector"]
