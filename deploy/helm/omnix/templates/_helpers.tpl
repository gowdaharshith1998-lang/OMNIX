{{- define "omnix.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "omnix.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
{{- end -}}

{{- define "omnix.api.image" -}}
{{- $r := .Values.global.image.registry -}}
{{- $repo := .Values.api.image.repository -}}
{{- $tag := default .Chart.AppVersion .Values.api.image.tag -}}
{{- printf "%s/%s:%s" $r $repo $tag -}}
{{- end -}}

{{- define "omnix.worker.image" -}}
{{- $r := .Values.global.image.registry -}}
{{- $repo := .Values.worker.image.repository -}}
{{- $tag := default .Chart.AppVersion .Values.worker.image.tag -}}
{{- printf "%s/%s:%s" $r $repo $tag -}}
{{- end -}}

{{- define "omnix.studio.image" -}}
{{- $r := .Values.global.image.registry -}}
{{- $repo := .Values.studio.image.repository -}}
{{- $tag := default .Chart.AppVersion .Values.studio.image.tag -}}
{{- printf "%s/%s:%s" $r $repo $tag -}}
{{- end -}}

{{- define "omnix.verifier.image" -}}
{{- $r := .Values.global.image.registry -}}
{{- $repo := .Values.verifier.image.repository -}}
{{- $tag := default .Chart.AppVersion .Values.verifier.image.tag -}}
{{- printf "%s/%s:%s" $r $repo $tag -}}
{{- end -}}

{{/* Resolve the OMNIX database URL.
     - external.dsn wins (production Aurora / RDS / CloudSQL).
     - subchart.enabled + postgres.enabled → in-cluster CloudNativePG -rw service.
     - otherwise fall back to sqlite (single-pod dev). */}}
{{- define "omnix.postgres.dsn" -}}
{{- if .Values.postgres.external.dsn -}}
{{ .Values.postgres.external.dsn }}
{{- else if and .Values.postgres.enabled .Values.postgres.subchart.enabled -}}
postgresql+asyncpg://{{ .Values.postgres.auth.username | default "omnix" }}:$(POSTGRES_PASSWORD)@{{ include "omnix.fullname" . }}-postgres-rw:5432/{{ .Values.postgres.auth.database | default "omnix" }}
{{- else -}}
sqlite+aiosqlite:////data/omnix.db
{{- end -}}
{{- end -}}

{{/* Resolve the OMNIX S3 endpoint URL.
     - subchart.enabled → in-cluster bitnami MinIO Service (port 9000).
     - otherwise use the operator-supplied storage.s3.endpoint. */}}
{{- define "omnix.s3.endpoint" -}}
{{- if and (eq (.Values.api.env.OMNIX_STORAGE_BACKEND | toString) "minio") .Values.minio.subchart.enabled -}}
http://{{ .Release.Name }}-minio:9000
{{- else if .Values.storage -}}
{{- .Values.storage.s3.endpoint | default "" -}}
{{- end -}}
{{- end -}}

{{/* Static-mode facade cluster list — one legacy + one candidate per unit
     in .Values.facade.staticUnits. Mode B fallback for air-gapped /
     regulated environments where filesystem CDS is disallowed. */}}
{{- define "omnix.facade.staticClusters" -}}
{{- $legacyHost := .Values.facade.legacyService | splitList ":" | first -}}
{{- $legacyPort := .Values.facade.legacyService | splitList ":" | last | atoi -}}
{{- range $unit := .Values.facade.staticUnits }}
- name: legacy_{{ $unit }}
  type: STRICT_DNS
  connect_timeout: 1s
  lb_policy: ROUND_ROBIN
  dns_lookup_family: V4_ONLY
  load_assignment:
    cluster_name: legacy_{{ $unit }}
    endpoints:
    - lb_endpoints:
      - endpoint:
          address:
            socket_address:
              address: {{ $legacyHost | quote }}
              port_value: {{ $legacyPort }}
{{- $candTarget := replace "{unit}" $unit $.Values.facade.candidateServiceTemplate -}}
{{- $candHost := $candTarget | splitList ":" | first }}
{{- $candPort := $candTarget | splitList ":" | last | atoi }}
- name: candidate_{{ $unit }}
  type: LOGICAL_DNS
  connect_timeout: 1s
  lb_policy: ROUND_ROBIN
  dns_lookup_family: V4_ONLY
  load_assignment:
    cluster_name: candidate_{{ $unit }}
    endpoints:
    - lb_endpoints:
      - endpoint:
          address:
            socket_address:
              address: {{ $candHost | quote }}
              port_value: {{ $candPort }}
{{- end }}
{{- end -}}

{{/* Compose the Trillian MySQL URI for Rekor's logserver / logsigner sidecars. */}}
{{- define "omnix.rekor.trillianMysqlUri" -}}
{{- $cfg := .Values.rekor.trillian.externalMysql -}}
{{- if $cfg.host -}}
trillian:trillian@tcp({{ $cfg.host }}:{{ $cfg.port }})/{{ $cfg.database }}
{{- else -}}
trillian:trillian@tcp({{ include "omnix.fullname" . }}-rekor-mysql:3306)/trillian
{{- end -}}
{{- end -}}
