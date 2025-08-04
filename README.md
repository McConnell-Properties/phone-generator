name: Hotel Lock Code Generator

on:
  schedule:
    # Run daily at 6:00 AM UTC (adjust timezone as needed)
    - cron: '0 6 * * *'
    # Run twice daily at 9 AM and 6 PM UTC
    # - cron: '0 9,18 * * *'
  
  # Allow manual triggering from GitHub UI
  workflow_dispatch:

jobs:
  generate-lock-codes:
    runs-on: ubuntu-latest
    
    steps:
    - name: Checkout repository
      uses: actions/checkout@v4
    
    - name: Set up Python 3.9
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install requests
    
    - name: Run lock code generator
      run: |
        python improved_phone_generator.py
      env:
        # Add any environment variables if needed
        PYTHONUNBUFFERED: 1
    
    - name: Upload CSV reports as artifacts
      uses: actions/upload-artifact@v4
      if: always()  # Upload even if script fails
      with:
        name: lock-code-reports-${{ github.run_number }}
        path: |
          simple_phone_report_*.csv
        retention-days: 30
    
    - name: Upload logs as artifacts
      uses: actions/upload-artifact@v4
      if: always()
      with:
        name: execution-logs-${{ github.run_number }}
        path: |
          *.log
        retention-days: 7
    
    # Optional: Send notification on failure
    - name: Notify on failure
      if: failure()
      run: |
        echo "Lock code generation failed!"
        echo "Check the logs in the Actions tab for details."
        # You could add Slack/email notifications here if needed
