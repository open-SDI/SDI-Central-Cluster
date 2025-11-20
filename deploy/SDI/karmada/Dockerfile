FROM golang:1.24.5 AS builder
WORKDIR /src
ENV CGO_ENABLED=0 GOOS=linux
ARG GOARCH=amd64

COPY go.mod go.sum ./
RUN go mod download

COPY . .

RUN GOARCH=${GOARCH} go build -trimpath -ldflags="-s -w" -o /out/sdi-scheduler ./cmd/sdi-scheduler

FROM gcr.io/distroless/static:nonroot
COPY --from=builder --chown=nonroot:nonroot /out/sdi-scheduler /sdi-scheduler
USER nonroot:nonroot
ENTRYPOINT ["/sdi-scheduler"]
