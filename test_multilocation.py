#!/usr/bin/env python3
"""
Comprehensive Multi-Location Query Test Suite
Tests the rewritten synthesis function to ensure each location is analyzed independently
"""

import requests
import json
import time
from datetime import datetime

API_URL = "https://intuition-api.onrender.com"

class TestResults:
    def __init__(self):
        self.results = []
        self.passed = 0
        self.failed = 0

    def add_result(self, test_name, passed, expected, actual, details=""):
        self.results.append({
            "test": test_name,
            "passed": passed,
            "expected": expected,
            "actual": actual,
            "details": details
        })
        if passed:
            self.passed += 1
            print(f"✓ {test_name}")
        else:
            self.failed += 1
            print(f"✗ {test_name}")
            print(f"  Expected: {expected}")
            print(f"  Got: {actual}")
            if details:
                print(f"  Details: {details}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*70}")
        print(f"FINAL RESULTS: {self.passed}/{total} tests passed ({100*self.passed//total}%)")
        print(f"{'='*70}\n")
        return self.failed == 0


def test_multi_location_germany_japan():
    """Test the user's original question: Germany karaoke + Japan karaoke"""
    results = TestResults()

    print(f"\n{'='*70}")
    print("TEST: Multi-Location Query (Germany + Japan Karaoke)")
    print(f"{'='*70}\n")

    question = """I have two client entertainment events.
    First, I am taking a client in Germany to a Karaoke bar.
    Second, I am taking a client in Japan to a karaoke bar.
    Please classify the risk for each event."""

    try:
        response = requests.post(
            f"{API_URL}/query",
            json={"question": question},
            timeout=30
        )

        if response.status_code != 200:
            results.add_result(
                "API Response Status",
                False,
                "200",
                response.status_code,
                f"Response: {response.text[:200]}"
            )
            return results

        data = response.json()

        # Check that response has required fields
        required_fields = ["user_friendly_output", "query_decomposition", "regions_analyzed"]
        for field in required_fields:
            results.add_result(
                f"Response has '{field}'",
                field in data,
                f"Present",
                f"Present" if field in data else "Missing"
            )

        # Check query decomposition contains both Germany and Japan
        decomposition = data.get("query_decomposition", [])
        entities = [d.get("entity", "") for d in decomposition]

        has_germany = any("germany" in e.lower() for e in entities)
        has_japan = any("japan" in e.lower() or "tokyo" in e.lower() for e in entities)

        results.add_result(
            "Query decomposition includes Germany",
            has_germany,
            "Germany detected",
            f"Found entities: {entities}"
        )

        results.add_result(
            "Query decomposition includes Japan",
            has_japan,
            "Japan detected",
            f"Found entities: {entities}"
        )

        # Check user-friendly output mentions both locations
        output = data.get("user_friendly_output", "")

        has_germany_analysis = "GERMANY" in output.upper()
        has_japan_analysis = "JAPAN" in output.upper()

        results.add_result(
            "Output includes Germany analysis",
            has_germany_analysis,
            "Germany section in output",
            "Germany mentioned" if has_germany_analysis else "Germany NOT in output"
        )

        results.add_result(
            "Output includes Japan analysis",
            has_japan_analysis,
            "Japan section in output",
            "Japan mentioned" if has_japan_analysis else "Japan NOT in output"
        )

        # Print the actual output for manual review
        print(f"\nGenerated Output:\n{'-'*70}")
        print(output)
        print(f"{'-'*70}\n")

        # Check compliance status
        compliance = data.get("compliance_status", "")
        print(f"Compliance Status: {compliance}")
        print(f"Query Decomposition: {len(decomposition)} locations detected")
        print(f"Regions Analyzed: {data.get('regions_analyzed', [])}\n")

    except Exception as e:
        results.add_result(
            "API Request",
            False,
            "Successful request",
            f"Error: {str(e)}"
        )

    return results


def test_single_location_germany():
    """Test single-location query: Germany only"""
    results = TestResults()

    print(f"\n{'='*70}")
    print("TEST: Single Location (Germany Only)")
    print(f"{'='*70}\n")

    question = "Can I take a client to karaoke in Germany?"

    try:
        response = requests.post(
            f"{API_URL}/query",
            json={"question": question},
            timeout=30
        )

        data = response.json()
        output = data.get("user_friendly_output", "")

        # Should NOT analyze APAC-only policies for Germany
        has_apac_reference = "APAC" in output or "Asia-Pacific" in output.upper()
        results.add_result(
            "Germany query doesn't show APAC policies",
            not has_apac_reference,
            "No APAC in output",
            "APAC mentioned" if has_apac_reference else "No APAC mentioned"
        )

        print(f"Output excerpt:\n{output[:500]}\n")

    except Exception as e:
        results.add_result(
            "API Request",
            False,
            "Successful",
            f"Error: {str(e)}"
        )

    return results


def test_single_location_japan():
    """Test single-location query: Japan (APAC)"""
    results = TestResults()

    print(f"\n{'='*70}")
    print("TEST: Single Location (Japan - APAC Region)")
    print(f"{'='*70}\n")

    question = "Can I take a client to karaoke in Japan?"

    try:
        response = requests.post(
            f"{API_URL}/query",
            json={"question": question},
            timeout=30
        )

        data = response.json()
        output = data.get("user_friendly_output", "")

        # Japan query SHOULD include APAC policy restrictions
        has_risk_content = "CRITICAL" in output or "BLOCK" in output or "HIGH" in output
        results.add_result(
            "Japan query detects risk/restrictions",
            has_risk_content,
            "Shows risk indicators",
            "Has risk indicators" if has_risk_content else "No risk indicators"
        )

        print(f"Output excerpt:\n{output[:500]}\n")

    except Exception as e:
        results.add_result(
            "API Request",
            False,
            "Successful",
            f"Error: {str(e)}"
        )

    return results


def test_multiple_locations_apac():
    """Test multi-location in same region: Singapore + Hong Kong"""
    results = TestResults()

    print(f"\n{'='*70}")
    print("TEST: Multi-Location (Singapore + Hong Kong - Both APAC)")
    print(f"{'='*70}\n")

    question = "I have client entertainment in Singapore and Hong Kong. What are the restrictions?"

    try:
        response = requests.post(
            f"{API_URL}/query",
            json={"question": question},
            timeout=30
        )

        data = response.json()
        decomposition = data.get("query_decomposition", [])

        results.add_result(
            "Query decomposed into multiple sub-queries",
            len(decomposition) > 1,
            "Multiple sub-queries",
            f"{len(decomposition)} sub-queries"
        )

        output = data.get("user_friendly_output", "")
        print(f"Output excerpt:\n{output[:500]}\n")

    except Exception as e:
        results.add_result(
            "API Request",
            False,
            "Successful",
            f"Error: {str(e)}"
        )

    return results


def main():
    print(f"\n{'='*70}")
    print(f"MULTI-LOCATION QUERY TEST SUITE")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"API URL: {API_URL}")
    print(f"{'='*70}")

    # Wait a moment for Render deployment to complete
    print("\nWaiting for server to be fully ready...")
    time.sleep(2)

    # Run all tests
    all_results = []

    all_results.append(test_multi_location_germany_japan())
    all_results.append(test_single_location_germany())
    all_results.append(test_single_location_japan())
    all_results.append(test_multiple_locations_apac())

    # Summary
    total_passed = sum(r.passed for r in all_results)
    total_failed = sum(r.failed for r in all_results)
    total = total_passed + total_failed

    print(f"\n{'='*70}")
    print(f"OVERALL RESULTS: {total_passed}/{total} tests passed")
    print(f"{'='*70}\n")

    if total_failed == 0:
        print("✓ ALL TESTS PASSED! Multi-location queries are working correctly.")
    else:
        print(f"✗ {total_failed} test(s) failed. Review output above.")

    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    exit(main())
