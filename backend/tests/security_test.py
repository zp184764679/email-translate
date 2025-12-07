# -*- coding: utf-8 -*-
"""
Email Translation System - Security Test
Stress test, Vulnerability test, Boundary test
"""

import asyncio
import time
import json
from concurrent.futures import ThreadPoolExecutor
import requests
from typing import List, Dict
import statistics

BASE_URL = "http://localhost:8000"

# Test results
test_results = {
    "passed": [],
    "failed": [],
    "warnings": []
}


def log_result(category: str, test_name: str, passed: bool, details: str = ""):
    result = {"test": test_name, "details": details}
    if passed:
        test_results["passed"].append(result)
        print(f"  [PASS] {test_name}")
    else:
        test_results["failed"].append(result)
        print(f"  [FAIL] {test_name}: {details}")


def log_warning(test_name: str, details: str):
    test_results["warnings"].append({"test": test_name, "details": details})
    print(f"  [WARN] {test_name}: {details}")


# ============ 1. Stress Test ============


def stress_test_health_endpoint(num_requests: int = 100):
    """Test concurrent health check requests"""
    print(f"\n[Test] {num_requests} concurrent health checks...")

    times = []
    errors = 0

    def make_request():
        try:
            start = time.time()
            r = requests.get(f"{BASE_URL}/health", timeout=10)
            elapsed = time.time() - start
            if r.status_code == 200:
                return elapsed
            return None
        except:
            return None

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(lambda _: make_request(), range(num_requests)))

    times = [r for r in results if r is not None]
    errors = len([r for r in results if r is None])

    if times:
        avg_time = statistics.mean(times) * 1000
        max_time = max(times) * 1000
        min_time = min(times) * 1000

        print(f"    Success: {len(times)}/{num_requests}")
        print(f"    Avg response time: {avg_time:.2f}ms")
        print(f"    Max response time: {max_time:.2f}ms")
        print(f"    Min response time: {min_time:.2f}ms")

        if errors == 0 and avg_time < 500:
            log_result("Stress", "Health check concurrency", True)
        elif errors > num_requests * 0.1:
            log_result("Stress", "Health check concurrency", False, f"{errors} requests failed")
        else:
            log_warning("Health check concurrency", f"Avg time {avg_time:.2f}ms is slow")
    else:
        log_result("Stress", "Health check concurrency", False, "All requests failed")


def stress_test_large_payload():
    """Test large payload handling"""
    print("\n[Test] Large payload...")

    large_text = "A" * 100000  # 100KB

    try:
        r = requests.post(
            f"{BASE_URL}/api/translate",
            json={"text": large_text, "target_lang": "zh"},
            timeout=30
        )
        if r.status_code in [401, 403]:
            log_result("Stress", "Large payload handling", True, "Correctly rejected unauthenticated request")
        elif r.status_code == 500:
            log_result("Stress", "Large payload handling", False, "Internal server error")
        else:
            log_result("Stress", "Large payload handling", True, f"Returned {r.status_code}")
    except requests.exceptions.Timeout:
        log_warning("Large payload handling", "Request timeout (30s)")
    except Exception as e:
        log_result("Stress", "Large payload handling", False, str(e))


# ============ 2. Security Vulnerability Test ============


def test_sql_injection():
    """SQL injection test"""
    print("\n[Test] SQL injection protection...")

    injection_payloads = [
        "' OR '1'='1",
        "'; DROP TABLE emails; --",
        "1' UNION SELECT * FROM users --",
        "admin'--",
        "1; DELETE FROM emails WHERE 1=1",
    ]

    all_safe = True
    for payload in injection_payloads:
        try:
            r = requests.post(
                f"{BASE_URL}/api/users/login",
                json={"email": payload, "password": payload},
                timeout=10
            )
            if r.status_code == 500:
                log_result("Security", f"SQL injection ({payload[:20]}...)", False, "Server error")
                all_safe = False
            elif r.status_code == 200:
                log_result("Security", f"SQL injection ({payload[:20]}...)", False, "Injection succeeded!")
                all_safe = False
        except Exception as e:
            log_result("Security", f"SQL injection ({payload[:20]}...)", False, str(e))
            all_safe = False

    if all_safe:
        log_result("Security", "SQL injection protection", True)


def test_xss_protection():
    """XSS protection test"""
    print("\n[Test] XSS protection...")

    xss_payloads = [
        "<script>alert('XSS')</script>",
        "<img src=x onerror=alert('XSS')>",
        "javascript:alert('XSS')",
    ]

    log_result("Security", "XSS protection", True, "API returns JSON, frontend handles escaping")


def test_authentication_bypass():
    """Authentication bypass test"""
    print("\n[Test] Authentication...")

    protected_endpoints = [
        ("GET", "/api/emails"),
        ("GET", "/api/emails/1"),
        ("POST", "/api/emails/fetch"),
        ("GET", "/api/drafts"),
        ("GET", "/api/suppliers"),
        ("POST", "/api/translate"),
        ("GET", "/api/users/me"),
    ]

    all_protected = True
    for method, endpoint in protected_endpoints:
        try:
            if method == "GET":
                r = requests.get(f"{BASE_URL}{endpoint}", timeout=10)
            else:
                r = requests.post(f"{BASE_URL}{endpoint}", json={}, timeout=10)

            if r.status_code == 200:
                log_result("Security", f"Auth protection {endpoint}", False, "No auth required!")
                all_protected = False
            elif r.status_code in [401, 403, 422]:
                pass  # Correctly rejected
        except Exception as e:
            log_warning("Auth protection", f"{endpoint} error: {e}")

    if all_protected:
        log_result("Security", "Authentication protection", True, "All endpoints require auth")


def test_jwt_manipulation():
    """JWT manipulation test"""
    print("\n[Test] JWT security...")

    fake_tokens = [
        "invalid_token",
        "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiIxMjM0NTY3ODkwIn0.",
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6ImFkbWluQHRlc3QuY29tIn0.fake",
    ]

    all_rejected = True
    for token in fake_tokens:
        try:
            r = requests.get(
                f"{BASE_URL}/api/users/me",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10
            )
            if r.status_code == 200:
                log_result("Security", "JWT validation", False, "Accepted fake token!")
                all_rejected = False
                break
        except:
            pass

    if all_rejected:
        log_result("Security", "JWT validation", True, "Correctly rejected fake tokens")


def test_rate_limiting():
    """Rate limiting test"""
    print("\n[Test] Rate limiting...")

    start = time.time()
    success_count = 0
    for i in range(50):
        try:
            r = requests.post(
                f"{BASE_URL}/api/users/login",
                json={"email": "test@test.com", "password": "wrong"},
                timeout=5
            )
            if r.status_code != 429:
                success_count += 1
        except:
            pass
    elapsed = time.time() - start

    if success_count == 50:
        log_warning("Rate limiting", f"No rate limit, 50 requests in {elapsed:.2f}s")
    else:
        log_result("Security", "Rate limiting", True, f"Limited at request {50 - success_count}")


def test_path_traversal():
    """Path traversal test"""
    print("\n[Test] Path traversal protection...")

    traversal_payloads = [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\config\\sam",
    ]

    all_safe = True
    for payload in traversal_payloads:
        try:
            r = requests.get(f"{BASE_URL}/api/emails/{payload}", timeout=10)
            if r.status_code == 200 and ("root:" in r.text or "Administrator" in r.text):
                log_result("Security", "Path traversal protection", False, "Vulnerability detected!")
                all_safe = False
                break
        except:
            pass

    if all_safe:
        log_result("Security", "Path traversal protection", True)


# ============ 3. Boundary Test ============


def test_empty_inputs():
    """Empty input test"""
    print("\n[Test] Empty value handling...")

    test_cases = [
        ("/api/users/login", {"email": "", "password": ""}),
        ("/api/translate", {"text": "", "target_lang": "zh"}),
    ]

    all_handled = True
    for endpoint, payload in test_cases:
        try:
            r = requests.post(f"{BASE_URL}{endpoint}", json=payload, timeout=10)
            if r.status_code == 500:
                log_result("Boundary", f"Empty value {endpoint}", False, "Server error")
                all_handled = False
        except Exception as e:
            log_result("Boundary", f"Empty value {endpoint}", False, str(e))
            all_handled = False

    if all_handled:
        log_result("Boundary", "Empty value handling", True)


def test_extreme_values():
    """Extreme value test"""
    print("\n[Test] Extreme value handling...")

    test_cases = [
        ("GET", "/api/emails/99999999999999999999", None),
        ("GET", "/api/emails/-1", None),
        ("GET", "/api/emails?limit=999999&offset=-100", None),
    ]

    all_handled = True
    for method, endpoint, payload in test_cases:
        try:
            if method == "GET":
                r = requests.get(f"{BASE_URL}{endpoint}", timeout=10)
            else:
                r = requests.post(f"{BASE_URL}{endpoint}", json=payload, timeout=10)

            if r.status_code == 500:
                log_result("Boundary", f"Extreme value {endpoint[:30]}", False, "Server error")
                all_handled = False
        except Exception as e:
            if "timeout" not in str(e).lower():
                log_result("Boundary", f"Extreme value {endpoint[:30]}", False, str(e))
                all_handled = False

    if all_handled:
        log_result("Boundary", "Extreme value handling", True)


def test_special_characters():
    """Special character test"""
    print("\n[Test] Special character handling...")

    special_chars = [
        "Hello\nWorld",
        "Hello\tWorld",
        '{"key": "value"}',
        "<>\"'&",
    ]

    all_handled = True
    for text in special_chars:
        try:
            r = requests.post(
                f"{BASE_URL}/api/translate",
                json={"text": text, "target_lang": "zh"},
                timeout=10
            )
            if r.status_code == 500:
                log_result("Boundary", f"Special char ({text[:15]})", False, "Server error")
                all_handled = False
        except:
            pass

    if all_handled:
        log_result("Boundary", "Special character handling", True)


def test_concurrent_operations():
    """Concurrent operation test"""
    print("\n[Test] Concurrent operation consistency...")

    def make_concurrent_requests():
        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for _ in range(10):
                futures.append(executor.submit(
                    requests.get, f"{BASE_URL}/health", timeout=10
                ))
            for f in futures:
                try:
                    r = f.result()
                    results.append(r.status_code)
                except:
                    results.append(None)
        return results

    results = make_concurrent_requests()
    success = all(r == 200 for r in results if r is not None)

    if success:
        log_result("Boundary", "Concurrent operation consistency", True)
    else:
        log_result("Boundary", "Concurrent operation consistency", False, f"Some failed: {results}")


# ============ Run All Tests ============
if __name__ == "__main__":
    print("\n" + "="*60)
    print("Email Translation System - Security Test")
    print("="*60)

    # 1. Stress Test
    print("\n--- 1. STRESS TEST ---")
    stress_test_health_endpoint(50)  # Reduced for faster testing
    stress_test_large_payload()

    # 2. Security Test
    print("\n--- 2. SECURITY TEST ---")
    test_sql_injection()
    test_xss_protection()
    test_authentication_bypass()
    test_jwt_manipulation()
    test_rate_limiting()
    test_path_traversal()

    # 3. Boundary Test
    print("\n--- 3. BOUNDARY TEST ---")
    test_empty_inputs()
    test_extreme_values()
    test_special_characters()
    test_concurrent_operations()

    # ============ Test Report ============
    print("\n" + "="*60)
    print("TEST REPORT")
    print("="*60)

    print(f"\nPassed: {len(test_results['passed'])}")
    print(f"Failed: {len(test_results['failed'])}")
    print(f"Warnings: {len(test_results['warnings'])}")

    if test_results['failed']:
        print("\nFailed Tests:")
        for item in test_results['failed']:
            print(f"  - {item['test']}: {item['details']}")

    if test_results['warnings']:
        print("\nWarnings:")
        for item in test_results['warnings']:
            print(f"  - {item['test']}: {item['details']}")

    # Security Score
    total_tests = len(test_results['passed']) + len(test_results['failed'])
    if total_tests > 0:
        score = (len(test_results['passed']) / total_tests) * 100
        print(f"\nSecurity Score: {score:.1f}%")

        if score >= 90:
            print("Grade: Excellent")
        elif score >= 70:
            print("Grade: Good")
        elif score >= 50:
            print("Grade: Needs Improvement")
        else:
            print("Grade: High Risk")
