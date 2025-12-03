#!/usr/bin/env python3
"""
Validation Script for Hallucination Prevention
Tests the compliance system to verify Gold Standard Logic is working
"""

import json
import requests
import sys
from datetime import datetime

# Configuration
BACKEND_URL = "https://intuition-api.onrender.com"
FRONTEND_URL = "https://intuition-lab.vercel.app/compliance"

# Color codes for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"

class HalluccinationValidator:
    def __init__(self):
        self.backend_url = BACKEND_URL
        self.results = []
        self.hallucination_detected = False

    def log(self, message, level="info"):
        """Log message with color coding"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        if level == "success":
            print(f"{GREEN}✓ [{timestamp}] {message}{RESET}")
        elif level == "error":
            print(f"{RED}✗ [{timestamp}] {message}{RESET}")
        elif level == "warning":
            print(f"{YELLOW}⚠ [{timestamp}] {message}{RESET}")
        elif level == "info":
            print(f"{BLUE}ℹ [{timestamp}] {message}{RESET}")
        elif level == "test":
            print(f"{BOLD}{message}{RESET}")

    def check_backend_health(self):
        """Verify backend is running"""
        self.log("Checking backend health...", "info")
        try:
            response = requests.get(f"{self.backend_url}/", timeout=5)
            if response.status_code == 200:
                self.log("Backend is running", "success")
                return True
            else:
                self.log(f"Backend returned status {response.status_code}", "error")
                return False
        except requests.exceptions.ConnectionError:
            self.log(f"Cannot connect to {self.backend_url}", "error")
            return False
        except Exception as e:
            self.log(f"Health check error: {e}", "error")
            return False

    def check_vector_store(self):
        """Verify documents are uploaded"""
        self.log("Checking vector store status...", "info")
        try:
            response = requests.get(f"{self.backend_url}/health", timeout=5)
            if response.status_code == 200:
                data = response.json()
                doc_count = data.get("document_count", 0)
                chunk_count = data.get("chunk_count", 0)

                if doc_count == 0:
                    self.log("Vector store is EMPTY - Documents need to be uploaded", "warning")
                    return False
                else:
                    self.log(f"Vector store ready: {doc_count} documents, {chunk_count} chunks", "success")
                    return True
            else:
                self.log(f"Health check returned {response.status_code}", "warning")
                return False
        except Exception as e:
            self.log(f"Vector store check error: {e}", "warning")
            return False

    def test_query(self, query, location, expected_risk_level, test_name):
        """
        Test a single query and check for hallucinations

        Args:
            query: Question to ask
            location: Geographic location being tested
            expected_risk_level: Expected risk level (LOW, MODERATE, HIGH, CRITICAL)
            test_name: Name of the test case
        """
        self.log(f"\n{BOLD}TEST: {test_name}{RESET}", "test")
        self.log(f"Location: {location}", "info")
        self.log(f"Query: {query}", "info")

        try:
            response = requests.post(
                f"{self.backend_url}/query",
                json={"question": query},
                timeout=10
            )

            if response.status_code != 200:
                self.log(f"Query failed with status {response.status_code}", "error")
                return False

            data = response.json()

            # Extract risk classification
            risk_class = data.get("risk_classification", {})
            actual_risk_level = risk_class.get("risk_level", "UNKNOWN").upper()
            violation_summary = risk_class.get("violation_summary", "")
            detailed_analysis = risk_class.get("detailed_analysis", "")

            # Combine text to check for hallucinations
            full_response = f"{violation_summary} {detailed_analysis}"

            # Log findings
            self.log(f"Risk Level: {actual_risk_level}", "info")
            self.log(f"Violation Summary: {violation_summary}", "info")

            # Validate risk level
            if actual_risk_level != expected_risk_level:
                self.log(
                    f"Risk level mismatch! Expected {expected_risk_level}, got {actual_risk_level}",
                    "error"
                )
                return False
            else:
                self.log(f"Risk level correct ✓", "success")

            # Check for hallucination patterns
            hallucination_patterns = [
                ("including Germany", "adding non-existent Germany to response"),
                ("including Japan", "adding non-existent Japan to response"),
                ("which includes Germany", "inferring Germany scope"),
                ("which includes Japan", "inferring Japan scope"),
                (", Germany and Japan", "mixing locations incorrectly"),
                ("Germany ... Japan", "geographic inference"),
            ]

            found_hallucinations = []
            for pattern, description in hallucination_patterns:
                if pattern.lower() in full_response.lower():
                    found_hallucinations.append(f"{pattern} ({description})")

            if found_hallucinations:
                self.log("HALLUCINATIONS DETECTED:", "error")
                for h in found_hallucinations:
                    self.log(f"  - {h}", "error")
                self.hallucination_detected = True
                return False
            else:
                self.log("No hallucination patterns detected ✓", "success")

            # Check for policy scope matching
            if location == "Germany":
                # Germany should NOT see APAC-specific policies
                if "APAC" in full_response and expected_risk_level == "LOW":
                    self.log("WARNING: APAC mentioned for Germany (scope filtering issue)", "warning")
                    return False
            elif location == "Japan":
                # Japan should see APAC policies
                if "APAC" not in full_response and expected_risk_level == "CRITICAL":
                    self.log("WARNING: APAC not mentioned for Japan (expected in response)", "warning")

            self.log(f"Test PASSED for {location}", "success")
            return True

        except requests.exceptions.Timeout:
            self.log("Request timeout", "error")
            return False
        except Exception as e:
            self.log(f"Query error: {e}", "error")
            return False

    def run_test_suite(self):
        """Run complete hallucination prevention test suite"""
        self.log("\n" + "="*60, "info")
        self.log("HALLUCINATION PREVENTION VALIDATION SUITE", "test")
        self.log("="*60, "info")

        # Phase 1: Backend checks
        self.log("\n--- PHASE 1: Backend Health Check ---", "info")
        if not self.check_backend_health():
            self.log("\nBackend is not running. Cannot proceed with tests.", "error")
            return False

        # Phase 2: Vector store check
        self.log("\n--- PHASE 2: Vector Store Check ---", "info")
        if not self.check_vector_store():
            self.log("\nDocuments must be uploaded before running tests.", "warning")
            self.log("Upload documents via the compliance frontend at:", "info")
            self.log(FRONTEND_URL, "info")
            return False

        # Phase 3: Test cases
        self.log("\n--- PHASE 3: Hallucination Prevention Tests ---", "info")

        test_cases = [
            # Test Case 1: Germany Karaoke (should be LOW - not in APAC scope)
            {
                "query": "Can I take a client to Karaoke in Germany?",
                "location": "Germany",
                "expected_risk": "LOW",
                "name": "Germany Karaoke (Non-APAC Location)"
            },
            # Test Case 2: Japan Karaoke (should be CRITICAL - in APAC scope)
            {
                "query": "Can I take a client to Karaoke in Japan?",
                "location": "Japan",
                "expected_risk": "CRITICAL",
                "name": "Japan Karaoke (APAC Prohibited Activity)"
            },
            # Test Case 3: Germany Nightclub (should be LOW)
            {
                "query": "Can I take a client to a nightclub in Germany?",
                "location": "Germany",
                "expected_risk": "LOW",
                "name": "Germany Nightclub (Non-APAC Location)"
            },
            # Test Case 4: Combined locations
            {
                "query": "I have two events: Karaoke in Germany and Karaoke in Japan. Assess both.",
                "location": "Germany and Japan",
                "expected_risk": "MIXED",
                "name": "Combined Locations (Should analyze separately)"
            }
        ]

        results = []
        for i, test in enumerate(test_cases, 1):
            self.log(f"\n[Test {i}/{len(test_cases)}]", "info")

            # Skip MIXED test if we need specific validation
            if test["expected_risk"] == "MIXED":
                self.log("Skipping MIXED validation (manual review needed)", "warning")
                continue

            passed = self.test_query(
                test["query"],
                test["location"],
                test["expected_risk"],
                test["name"]
            )
            results.append({
                "test": test["name"],
                "passed": passed
            })

        # Phase 4: Summary
        self.log("\n--- PHASE 4: Test Summary ---", "info")
        passed_count = sum(1 for r in results if r["passed"])
        total_count = len(results)

        for result in results:
            status = "PASSED" if result["passed"] else "FAILED"
            symbol = "✓" if result["passed"] else "✗"
            color = GREEN if result["passed"] else RED
            self.log(f"{color}{symbol} {status}: {result['test']}{RESET}", "info")

        self.log(f"\n{BOLD}Results: {passed_count}/{total_count} tests passed{RESET}", "info")

        if self.hallucination_detected:
            self.log("\n⚠️  HALLUCINATIONS WERE DETECTED - System needs investigation", "error")
            return False

        if passed_count == total_count:
            self.log("\n🎉 All tests passed! Hallucination prevention is working correctly.", "success")
            return True
        else:
            self.log(f"\n⚠️  {total_count - passed_count} test(s) failed", "error")
            return False

    def print_instructions(self):
        """Print setup instructions"""
        print("\n" + "="*60)
        print("SETUP INSTRUCTIONS")
        print("="*60)
        print(f"\n1. Upload Documents:")
        print(f"   - Navigate to: {FRONTEND_URL}")
        print(f"   - Upload 3 test documents:")
        print(f"     • Global_Code_of_Business_Conduct_2025.docx")
        print(f"     • Global_Travel_and_Expense_Policy.docx")
        print(f"     • Regional_Addendum_APAC_High_Risk.docx")
        print(f"\n2. Run Validation:")
        print(f"   - python validate_hallucination_fix.py")
        print(f"\n3. Interpret Results:")
        print(f"   - All tests passed = Hallucination prevention working ✓")
        print(f"   - Any hallucination detected = System has issues ✗")
        print("="*60 + "\n")

def main():
    validator = HalluccinationValidator()

    # Print instructions
    if "--help" in sys.argv or "-h" in sys.argv:
        validator.print_instructions()
        return

    # Run test suite
    success = validator.run_test_suite()

    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
