import subprocess
import sys
import glob

skills_tests = glob.glob("/home/zhouwg/data1/project/OmicsClaw/skills/spatial/spatial-*/tests")
print("Found test dirs:", skills_tests)

for test_dir in skills_tests:
    print(f"\n--- Running tests in {test_dir} ---")
    res = subprocess.run([sys.executable, "-m", "pytest", test_dir], capture_output=True, text=True)
    if res.returncode == 0:
        print("SUCCESS")
    else:
        print("FAILED")
        print(res.stdout)
        if res.stderr:
            print("STDERR:")
            print(res.stderr)
