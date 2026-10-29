# code-review
Input: requirements, base commit, diff, relevant code/tests, verification log.
Steps: independently inspect correctness, boundary cases, auth/security, compatibility, test adequacy, maintainability; attempt reproduction if permitted.
Output: findings with severity, file/line, reasoning, reproduction, uncertainty; or "no findings identified" (not "verified correct").
Never approve on behalf of human or infer CI green without evidence.
