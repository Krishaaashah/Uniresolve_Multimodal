Add-Type -AssemblyName System.Speech

$mockDir = "c:\Users\krisha\Desktop\projects\Uniresolve\backend\app\connectors\mock_evidence"
$uploadDir = "c:\Users\krisha\Desktop\projects\Uniresolve\frontend\public\assets\uploads"

if (!(Test-Path $mockDir)) { New-Item -ItemType Directory -Path $mockDir -Force }
if (!(Test-Path $uploadDir)) { New-Item -ItemType Directory -Path $uploadDir -Force }

$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.Rate = 0  # Natural conversational rate
$synth.Volume = 100

function Generate-SpeechAudio($filename, $text) {
    $outPath = Join-Path $mockDir $filename
    Write-Host "Generating: $filename ..."
    $synth.SetOutputToWaveFile($outPath)
    $synth.Speak($text)
    Write-Host "  -> Created: $outPath (Size: $((Get-Item $outPath).Length) bytes)"
}

# 1. Primary Demo Grievance Audio Notes
Generate-SpeechAudio "voice_note.wav" "Hello, my name is Vikram Joshi, Customer ID CUST-10005. I tried to make a UPI payment of 4,500 rupees at a store for transaction TXN-10005-01. The payment timed out on the UPI gateway but the money was deducted from my savings account. Please reverse this transaction immediately."

Generate-SpeechAudio "demo_ivr_card_10004.wav" "Hello customer service, this is Neha Gupta, Customer ID CUST-10004. My debit card was suddenly blocked at the merchant terminal during transaction TXN-10004-02 for amount 3,500 rupees. Please unblock my card as soon as possible."

# 2. Evaluation Set Audio Files
Generate-SpeechAudio "eval_ivr_005.wav" "UPI payment of 4,500 rupees failed at store but amount debited from my account ref TXN-20004-A."
Generate-SpeechAudio "eval_ivr_025.wav" "Debit card swipe failed at POS terminal and money was deducted from balance ref TXN-20015-C."
Generate-SpeechAudio "eval_ivr_029.wav" "ATM machine se paise nahi nikle lekin account se 4,000 rupees debit ho gaye. Please resolve this issue."
Generate-SpeechAudio "eval_ivr_035.wav" "Pension khate me is month ki pension abhi tak credit nahi hui hai. Please look into this urgently."
Generate-SpeechAudio "eval_ivr_036.wav" "Debit card gum ho gaya hai par customer care number pe call connect nahi ho rahi. Please block my card."
Generate-SpeechAudio "eval_ivr_047.wav" "ATM madhun paise nighale nahit pan account madhun 5,000 rupees cut jhale. Please help quickly."
Generate-SpeechAudio "eval_ivr_054.wav" "ATM machine me cash atak gaya aur receipt me failed aaya but 4,000 rupees debit ho gaya ref TXN-20044-HG."
Generate-SpeechAudio "eval_ivr_068.wav" "Debit card ATM PIN blocked due to consecutive incorrect attempts by customer."
Generate-SpeechAudio "eval_ivr_095.wav" "Phishing collect request approved accidentally on UPI app, 75,000 rupees drained ref TXN-20088-F. Freeze my account immediately."
Generate-SpeechAudio "eval_ivr_098.wav" "ATM dispensed only 2,000 rupees cash but debited 10,000 rupees from account ref TXN-20089-A."
Generate-SpeechAudio "eval_ivr_111.wav" "Lost wallet with platinum credit card and debit card. Need immediate emergency blocking of all cards."
Generate-SpeechAudio "eval_ivr_118.wav" "Green PIN generation through SMS and IVR banking system worked perfectly on first attempt. Thank you."

$synth.Dispose()

Write-Host "All audio files generated successfully with audible high-volume voice synthesis."
