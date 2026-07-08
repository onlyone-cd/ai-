param(
  [string]$BaseUrl = "http://localhost:5001",
  [string]$Username = "admin",
  [string]$Password = "admin123"
)

$ErrorActionPreference = "Stop"
$script:Token = ""
$script:Results = @()
$script:TempCandidateId = $null
$script:TempJobId = $null
$script:TempEmployeeId = $null
$script:TempInterviewId = $null
$script:TempOfferId = $null

function Add-Result($Name, $Ok, $Detail = "") {
  $script:Results += [pscustomobject]@{ name = $Name; ok = [bool]$Ok; detail = $Detail }
}

function Invoke-Api($Method, $Path, $Body = $null) {
  $headers = @{}
  if ($script:Token) { $headers.Authorization = "Bearer $script:Token" }
  $params = @{
    Method = $Method
    Uri = "$BaseUrl$Path"
    Headers = $headers
  }
  if ($null -ne $Body) {
    $params.ContentType = "application/json"
    $params.Body = ($Body | ConvertTo-Json -Depth 30)
  }
  Invoke-RestMethod @params
}

function Test-Step($Name, [scriptblock]$Block) {
  try {
    $detail = & $Block
    Add-Result $Name $true ($detail -as [string])
  } catch {
    Add-Result $Name $false $_.Exception.Message
  }
}

function Download-Step($Name, $Path) {
  Test-Step $Name {
    $headers = @()
    if ($script:Token) { $headers = @("-H", "Authorization: Bearer $script:Token") }
    $code = & curl.exe -s -o NUL -w "%{http_code}" @headers "$BaseUrl$Path"
    if ($LASTEXITCODE -ne 0) { throw "curl failed with exit $LASTEXITCODE" }
    if ([int]$code -lt 200 -or [int]$code -ge 300) { throw "HTTP $code" }
    "HTTP $code"
  }
}

Test-Step "auth.login" {
  $login = Invoke-Api "POST" "/api/auth/login" @{ username = $Username; password = $Password }
  if (-not $login.data.token) { throw "missing token" }
  $script:Token = $login.data.token
  "role=$($login.data.user.role)"
}

Test-Step "system.core" {
  Invoke-Api "GET" "/api/auth/me" | Out-Null
  Invoke-Api "GET" "/api/auth/permissions" | Out-Null
  Invoke-Api "GET" "/api/system/readiness" | Out-Null
  Invoke-Api "GET" "/api/system/llm/status" | Out-Null
  Invoke-Api "GET" "/api/system/llm/usage?days=7" | Out-Null
  "ok"
}

Test-Step "candidate.import_and_detail" {
  $text = @"
Name: Smoke Candidate
Gender: Male
Phone: 13900001234
Email: smoke@example.com
Target: Java Backend Engineer
Experience: 4 years Java backend development, Spring Boot, MySQL, Redis, performance system, API integration.
Education: Bachelor, Computer Science
"@
  $created = Invoke-Api "POST" "/api/boss/candidates/batch-import" @{ items = @(@{ external_id = "smoke-candidate"; raw_text = $text }) }
  if (-not $created.data.items -or $created.data.items.Count -lt 1) { throw "candidate not imported" }
  $script:TempCandidateId = $created.data.items[0].id
  Invoke-Api "GET" "/api/candidates?limit=5" | Out-Null
  Invoke-Api "GET" "/api/candidates/$script:TempCandidateId" | Out-Null
  Invoke-Api "GET" "/api/tags" | Out-Null
  "candidate=$script:TempCandidateId"
}

Download-Step "candidate.resume_export" "/api/candidates/$script:TempCandidateId/resume.txt"

Test-Step "job.create_ai_match" {
  $job = Invoke-Api "POST" "/api/jobs" @{
    title = "Smoke Java Backend Engineer"
    city = "Shanghai"
    jd_text = "Build Java backend services. Requires Spring Boot, MySQL, Redis and more than 3 years of experience."
    skill_tags_raw = "Java 5`nSpring Boot 5`nMySQL 4`nRedis 4"
  }
  $script:TempJobId = $job.data.id
  Invoke-Api "GET" "/api/jobs?limit=5" | Out-Null
  Invoke-Api "GET" "/api/jobs/$script:TempJobId" | Out-Null
  Invoke-Api "POST" "/api/jobs/ai-generate" @{ title = "Java Backend Engineer"; city = "Shanghai" } | Out-Null
  Invoke-Api "POST" "/api/jobs/ai-calibrate" @{ title = "Java Backend Engineer"; jd_text = "Need Java, Spring Boot, MySQL and Redis." } | Out-Null
  $preview = Invoke-Api "GET" "/api/jobs/$script:TempJobId/match-preview?limit=5"
  if (-not $preview.data.items) { throw "no match preview items" }
  Invoke-Api "POST" "/api/jobs/$script:TempJobId/match" | Out-Null
  "job=$script:TempJobId"
}

Test-Step "pipeline.move_and_history" {
  Invoke-Api "POST" "/api/jobs/$script:TempJobId/batch-pipeline" @{ candidate_id = $script:TempCandidateId; stage = "pending"; note = "smoke" } | Out-Null
  Invoke-Api "GET" "/api/pipeline/$script:TempJobId/board" | Out-Null
  Invoke-Api "POST" "/api/pipeline/move" @{ candidate_id = $script:TempCandidateId; job_id = $script:TempJobId; stage = "business_review"; note = "smoke move" } | Out-Null
  Invoke-Api "GET" "/api/pipeline/$script:TempJobId/history/$script:TempCandidateId" | Out-Null
  Invoke-Api "GET" "/api/pipeline/overview" | Out-Null
  "ok"
}

Test-Step "internal_talent.organization_employee_analysis" {
  $tree = Invoke-Api "GET" "/api/organization/tree"
  if (-not $tree.data.items -or $tree.data.items.Count -lt 1) { throw "organization tree empty" }
  $unitId = $tree.data.items[0].id
  $createdUnit = Invoke-Api "POST" "/api/organization/units" @{ parent_id = $unitId; name = "Smoke Org Unit"; unit_type = "team"; headcount_plan = 2 }
  Invoke-Api "PATCH" "/api/organization/units/$($createdUnit.data.id)" @{ city = "Shanghai"; headcount_plan = 3 } | Out-Null
  Invoke-Api "DELETE" "/api/organization/units/$($createdUnit.data.id)" | Out-Null
  $employee = Invoke-Api "POST" "/api/employees/from-candidate" @{
    candidate_id = $script:TempCandidateId
    organization_unit_id = $unitId
    current_job_id = $script:TempJobId
    employee_no = "SMOKE-$script:TempCandidateId"
    level = "P6"
    salary_monthly_k = 18
    salary_months = 13
    hire_date = (Get-Date).ToString("yyyy-MM-dd")
  }
  $script:TempEmployeeId = $employee.data.id
  Invoke-Api "GET" "/api/employees/$script:TempEmployeeId" | Out-Null
  Invoke-Api "GET" "/api/organization/units/$unitId/employees" | Out-Null
  Invoke-Api "POST" "/api/employees/$script:TempEmployeeId/analyze-current-job" | Out-Null
  Invoke-Api "POST" "/api/employees/$script:TempEmployeeId/recommend-transfer" | Out-Null
  Invoke-Api "POST" "/api/employees/$script:TempEmployeeId/recommend-replacement" | Out-Null
  "employee=$script:TempEmployeeId"
}

Test-Step "interview.public_room_and_report" {
  $interviewers = Invoke-Api "GET" "/api/users/interviewers"
  if (-not $interviewers.data.items) { throw "no interviewer account" }
  $interviewerId = $interviewers.data.items[0].id
  $assignment = Invoke-Api "POST" "/api/interview/assignments" @{
    candidate_id = $script:TempCandidateId
    job_id = $script:TempJobId
    interviewer_id = $interviewerId
    round = "interview_first"
    scheduled_at = (Get-Date).AddDays(1).ToString("s")
  }
  $script:TempInterviewId = $assignment.data.id
  Invoke-Api "GET" "/api/interview/assignments/$script:TempInterviewId" | Out-Null
  Invoke-Api "POST" "/api/interview/assignments/$script:TempInterviewId/ai-plan" | Out-Null
  $link = Invoke-Api "POST" "/api/interview/assignments/$script:TempInterviewId/room-link"
  Invoke-Api "GET" "/api/public/interview-room/$($link.data.token)" | Out-Null
  Invoke-Api "POST" "/api/public/interview-room/$($link.data.token)/turn" @{ question = "Please introduce one backend project."; answer = "I owned Java backend APIs, database design and release work." } | Out-Null
  Invoke-Api "POST" "/api/public/interview-room/$($link.data.token)/complete" @{
    answers = @("I owned Java backend APIs, database design and release work.")
    messages = @(
      @{ role = "ai"; text = "Please introduce one backend project." },
      @{ role = "candidate"; text = "I owned Java backend APIs, database design and release work." }
    )
  } | Out-Null
  Invoke-Api "GET" "/api/interview/feedback?assignment_id=$script:TempInterviewId" | Out-Null
  "interview=$script:TempInterviewId"
}

Download-Step "interview.report_export" "/api/interview/assignments/$script:TempInterviewId/report.txt"

Test-Step "offer.lifecycle" {
  $offer = Invoke-Api "POST" "/api/offers" @{
    candidate_id = $script:TempCandidateId
    job_id = $script:TempJobId
    salary_min_k = 20
    salary_max_k = 30
    salary_months = 13
    city = "Shanghai"
    status = "draft"
    note = "smoke"
  }
  $script:TempOfferId = $offer.data.id
  Invoke-Api "GET" "/api/offers/$script:TempOfferId" | Out-Null
  Invoke-Api "PATCH" "/api/offers/$script:TempOfferId" @{ status = "sent" } | Out-Null
  "offer=$script:TempOfferId"
}

Download-Step "offer.letter_export" "/api/offers/$script:TempOfferId/letter.txt"

Test-Step "boss_bi_agent_tasks_exports" {
  Invoke-Api "GET" "/api/boss/status" | Out-Null
  Invoke-Api "GET" "/api/boss/candidates/inbox" | Out-Null
  Invoke-Api "GET" "/api/boss/jobs" | Out-Null
  Invoke-Api "GET" "/api/boss/sync/jobs?limit=5" | Out-Null
  Invoke-Api "GET" "/api/boss/jobs/$script:TempJobId/recommendations" | Out-Null
  Invoke-Api "POST" "/api/boss/candidates/ai-screen" @{ job_id = $script:TempJobId; candidate_ids = @($script:TempCandidateId) } | Out-Null
  Invoke-Api "GET" "/api/bi/overview?days=30" | Out-Null
  Invoke-Api "GET" "/api/tasks" | Out-Null
  Invoke-Api "GET" "/api/audit/logs?limit=5" | Out-Null
  Invoke-Api "GET" "/api/agent/tools" | Out-Null
  Invoke-Api "POST" "/api/agent/chat" @{ message = "How many candidates are in the talent pool?" } | Out-Null
  "ok"
}

foreach ($kind in @("candidates", "jobs", "interviews", "offers", "pipeline", "boss-drafts")) {
  Download-Step "exports.$kind" "/api/exports/$kind.csv"
}
Download-Step "boss.extension_download" "/api/boss/extension.zip"

Test-Step "cleanup" {
  if ($script:TempOfferId) { Invoke-Api "DELETE" "/api/offers/$script:TempOfferId" | Out-Null }
  if ($script:TempInterviewId) { Invoke-Api "DELETE" "/api/interview/assignments/$script:TempInterviewId" | Out-Null }
  if ($script:TempEmployeeId) { Invoke-Api "DELETE" "/api/employees/$script:TempEmployeeId" | Out-Null }
  if ($script:TempJobId) { Invoke-Api "DELETE" "/api/jobs/$script:TempJobId" | Out-Null }
  if ($script:TempCandidateId) { Invoke-Api "DELETE" "/api/candidates/$script:TempCandidateId" | Out-Null }
  "removed temp records"
}

$failed = @($script:Results | Where-Object { -not $_.ok })
$script:Results | Format-Table -AutoSize
if ($failed.Count) {
  Write-Host "Smoke failed: $($failed.Count) step(s)" -ForegroundColor Red
  exit 1
}
Write-Host "Smoke passed: $($script:Results.Count) step(s)" -ForegroundColor Green
