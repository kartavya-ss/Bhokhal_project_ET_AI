"""
Task 2 + Task 17: benchmark questions, run against the live system.
Write your 15-20 real ones here once you swap in the real 18 files.
"""
from query_engine import answer_question

BENCHMARK_QUESTIONS = [
    "Which deviation report is linked to the failed Batch 2602, and what machine caused it?",
    "What was the root cause of the Batch MP-PCM-2602 failure?",
    "Which SOP covers preventive maintenance for TCM-04, and was it followed?",
    "Who operated Machine TCM-04 and are they trained on it?",
    "Why did Batch 2601 pass when Batch 2602 failed?",
    "Who raised the deviation for Batch 2602 and who investigated it?",
    "What is the underlying cause behind the missed maintenance on TCM-04?",
]

if __name__ == "__main__":
    for i, q in enumerate(BENCHMARK_QUESTIONS, 1):
        print(f"\n{'='*80}\nQ{i}: {q}\n{'='*80}")
        result = answer_question(q)
        print(f"Facts retrieved: {len(result['facts'])} | Chunks retrieved: {len(result['chunks'])}")
        print(result["answer"][:400])
