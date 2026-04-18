"""Export session data as CSV."""

from tokenxray.parser import load_all_sessions


def run(args):
    sessions = load_all_sessions(args.path)
    sessions.sort(key=lambda s: s["cost"]["total"], reverse=True)

    print("session_id,project,turns,total_cost,cache_savings,input_tokens,"
          "output_tokens,cache_read,cache_create,model,duration_min")

    for s in sessions:
        dur = ""
        if s["start_time"] and s["end_time"]:
            dur = f"{(s['end_time'] - s['start_time']).total_seconds() / 60:.0f}"
        model = s["models_used"][0] if s["models_used"] else "unknown"
        print(
            f"{s['full_id']},{s['project']},{len(s['turns'])},"
            f"{s['cost']['total']:.4f},{s['cost']['cache_savings']:.4f},"
            f"{s['total_input']},{s['total_output']},"
            f"{s['total_cache_read']},{s['total_cache_create']},"
            f"{model},{dur}"
        )
