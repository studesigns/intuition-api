#!/usr/bin/env python3
"""
Comprehensive Test Execution Suite
Uploads documents and runs complete validation of hallucination prevention
"""

import requests
import json
import sys
from datetime import datetime
from pathlib import Path

# Color codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
RESET = "\033[0m"
BOLD = "\033[1m"

class ComprehensiveTestSuite:
    def __init__(self):
        self.backend_url = "https://intuition-api.onrender.com"
        self.test_results = []
        self.doc_dir = "/home/stu/Projects/intuition-api/test_docs"

    def log(self, message, level="info"):
        """Color-coded logging"""
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
            print(f"{MAGENTA}{BOLD}{'='*70}{RESET}")
            print(f"{MAGENTA}{BOLD}{message}{RESET}")
            print(f"{MAGENTA}{BOLD}{'='*70}{RESET}")
        elif level == "header":
            print(f"{BOLD}{BLUE}{message}{RESET}")

    def upload_documents(self):
        """Upload test documents to backend"""
        self.log("UPLOADING TEST DOCUMENTS", "test")

        doc_files = [
            "Global_Entertainment_Client_Relations_Policy.pdf",
            "Regional_Addendum_APAC_High_Risk_Activities.pdf",
            "Global_Business_Travel_Entertainment_Expenses_Policy.pdf"
        ]

        # Prepare files for multipart upload
        files_to_upload = []
        for doc_file in doc_files:
            doc_path = Path(self.doc_dir) / doc_file
            if not doc_path.exists():
                self.log(f"File not found: {doc_path}", "error")
                continue
            self.log(f"Preparing: {doc_file}", "info")
            files_to_upload.append(('files', open(doc_path, 'rb')))

        if not files_to_upload:
            self.log("No files to upload", "error")
            return False

        try:
            self.log(f"Uploading {len(files_to_upload)} files to backend...", "info")
            response = requests.post(
                f"{self.backend_url}/upload",
                files=files_to_upload,
                timeout=60
            )

            # Close all file handles
            for _, file_handle in files_to_upload:
                file_handle.close()

            if response.status_code == 200:
                data = response.json()
                self.log(f"Upload successful!", "success")
                self.log(f"  Files processed: {data.get('files_processed', 0)}", "info")
                self.log(f"  Chunks created: {data.get('chunks', 0)}", "info")
                self.log(f"  Regions detected: {data.get('regions_detected', [])}", "info")
                return True
            else:
                self.log(f"Upload failed ({response.status_code})", "error")
                self.log(f"Response: {response.text[:300]}", "error")
                return False

        except Exception as e:
            self.log(f"Upload error: {e}", "error")
            return False
        finally:
            # Ensure all files are closed
            for _, file_handle in files_to_upload:
                try:
                    file_handle.close()
                except:
                    pass

    def test_query(self, query_text, test_name, expected_result=None):
        """Execute a test query and validate response"""
        self.log(f"TEST: {test_name}", "test")
        self.log(f"Query: {query_text}", "info")

        try:
            response = requests.post(
                f"{self.backend_url}/query",
                json={"question": query_text},
                timeout=30
            )

            if response.status_code != 200:
                self.log(f"Query failed with status {response.status_code}", "error")
                return False

            data = response.json()
            self.log(f"Response received: {response.status_code}", "success")

            # Extract risk classification
            risk_class = data.get("risk_classification", {})
            risk_level = risk_class.get("risk_level", "UNKNOWN").upper()
            action = risk_class.get("action", "UNKNOWN").upper()
            violation_summary = risk_class.get("violation_summary", "")
            detailed_analysis = risk_class.get("detailed_analysis", "")

            self.log(f"Risk Level: {risk_level}", "info")
            self.log(f"Action: {action}", "info")
            self.log(f"Summary: {violation_summary[:100]}...", "info")

            # Check for expected result
            if expected_result:
                if expected_result["risk_level"] == risk_level:
                    self.log(f"✓ Risk level matches expected: {risk_level}", "success")
                else:
                    self.log(
                        f"✗ Risk level mismatch! Expected {expected_result['risk_level']}, got {risk_level}",
                        "error"
                    )
                    return False

                if expected_result.get("not_contain"):
                    full_text = violation_summary + " " + detailed_analysis
                    for phrase in expected_result["not_contain"]:
                        if phrase.lower() in full_text.lower():
                            self.log(f"✗ HALLUCINATION DETECTED: '{phrase}'", "error")
                            return False
                    self.log(f"✓ No hallucination phrases detected", "success")

            # Validate response structure
            sources = data.get("sources", [])
            self.log(f"Sources cited: {len(sources)}", "info")
            for source in sources[:2]:  # Show first 2
                doc = source.get("document", "Unknown")
                self.log(f"  - {doc}", "info")

            self.log(f"Test PASSED: {test_name}", "success")
            return True

        except requests.exceptions.Timeout:
            self.log("Request timeout", "error")
            return False
        except Exception as e:
            self.log(f"Test error: {e}", "error")
            return False

    def run_test_suite(self):
        """Execute complete test suite"""
        print(f"\n{BOLD}{MAGENTA}{'='*70}{RESET}")
        print(f"{BOLD}{MAGENTA}COMPREHENSIVE HALLUCINATION PREVENTION TEST SUITE{RESET}")
        print(f"{BOLD}{MAGENTA}{'='*70}{RESET}\n")

        # Phase 1: Upload documents
        if not self.upload_documents():
            self.log("Document upload failed. Cannot proceed with tests.", "error")
            return False

        # Phase 2: Allow processing time
        print()
        self.log("Waiting for document processing...", "info")
        import time
        time.sleep(3)

        # Phase 3: Run test cases
        print()
        self.log("EXECUTING TEST CASES", "test")

        test_cases = [
            # Test 1: Germany Karaoke (Should be LOW - not in APAC)
            {
                "query": "I'm taking a client to Karaoke in Germany. What's the compliance risk?",
                "name": "Germany Karaoke (Non-APAC Location)",
                "expected": {
                    "risk_level": "LOW",
                    "not_contain": ["APAC", "prohibited", "karaoke forbidden"]
                }
            },
            # Test 2: Japan Karaoke (Should be CRITICAL - in APAC, explicitly prohibited)
            {
                "query": "I'm taking a client to Karaoke in Japan. What's the compliance risk?",
                "name": "Japan Karaoke (APAC Prohibited)",
                "expected": {
                    "risk_level": "CRITICAL",
                    "not_contain": ["Germany", "including Germany"]
                }
            },
            # Test 3: China Nightclub (Should be CRITICAL - in APAC, prohibited)
            {
                "query": "Can I take a client to a nightclub in China for entertainment?",
                "name": "China Nightclub (APAC Prohibited)",
                "expected": {
                    "risk_level": "CRITICAL",
                    "not_contain": ["Germany", "Europe"]
                }
            },
            # Test 4: Vietnam Entertainment (Should be CRITICAL - in APAC)
            {
                "query": "Entertainment expense approval for Vietnam - client at a karaoke establishment.",
                "name": "Vietnam Karaoke Entertainment",
                "expected": {
                    "risk_level": "CRITICAL",
                    "not_contain": ["permitted", "allowed"]
                }
            },
            # Test 5: Thailand Nightclub (Should be CRITICAL - in APAC)
            {
                "query": "Taking a client to a nightclub in Thailand. Is this compliant?",
                "name": "Thailand Nightclub (APAC Prohibited)",
                "expected": {
                    "risk_level": "CRITICAL"
                }
            },
            # Test 6: France Golf (Should be LOW - not in APAC)
            {
                "query": "Can I take a client golfing in France?",
                "name": "France Golf (Permitted Activity)",
                "expected": {
                    "risk_level": "LOW",
                    "not_contain": ["prohibited", "karaoke"]
                }
            },
            # Test 7: Singapore Gambling (Should be MODERATE/CRITICAL - in APAC, restricted)
            {
                "query": "Is casino entertainment in Singapore acceptable for client entertainment?",
                "name": "Singapore Casino (APAC Restricted)",
                "expected": {
                    "risk_level": "CRITICAL"
                }
            },
            # Test 8: Germany Entertainment Policy (General question - Should reference global policy)
            {
                "query": "What are the entertainment policies for Germany?",
                "name": "Germany General Policy Query",
                "expected": {
                    "risk_level": "LOW"
                }
            },
            # Test 9: APAC Scope Test (Should explain APAC countries)
            {
                "query": "Which countries are covered by the APAC regional addendum?",
                "name": "APAC Scope Definition",
                "expected": {
                    "risk_level": "LOW"
                }
            },
            # Test 10: Multi-location (Germany and Japan)
            {
                "query": "I have client entertainment in two locations. Germany: karaoke bar. Japan: karaoke bar. Analyze both.",
                "name": "Multi-Location Analysis (Germany vs Japan)",
                "expected": {
                    "not_contain": ["including Germany and Japan", "Germany...Japan"]
                }
            }
        ]

        results = []
        for i, test in enumerate(test_cases, 1):
            print()
            self.log(f"[Test {i}/{len(test_cases)}]", "header")
            passed = self.test_query(
                test["query"],
                test["name"],
                test.get("expected")
            )
            results.append({
                "name": test["name"],
                "passed": passed
            })

        # Phase 4: Summary
        print()
        self.log("TEST SUMMARY", "test")

        passed_count = sum(1 for r in results if r["passed"])
        total_count = len(results)

        print()
        for result in results:
            status = "PASSED" if result["passed"] else "FAILED"
            symbol = "✓" if result["passed"] else "✗"
            color = GREEN if result["passed"] else RED
            print(f"{color}{symbol} {status}: {result['name']}{RESET}")

        print()
        self.log(f"FINAL RESULT: {passed_count}/{total_count} tests passed", "header")

        if passed_count == total_count:
            self.log("🎉 ALL TESTS PASSED - Hallucination Prevention is WORKING!", "success")
            return True
        elif passed_count >= (total_count * 0.8):
            self.log(f"⚠️  {passed_count}/{total_count} tests passed (80% threshold met)", "warning")
            self.log("System is mostly working but some issues detected", "warning")
            return True
        else:
            self.log(f"❌ {total_count - passed_count} test(s) failed", "error")
            return False

def main():
    suite = ComprehensiveTestSuite()
    success = suite.run_test_suite()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
