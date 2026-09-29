Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$targetFile = "c:\Users\krisha\Desktop\projects\Uniresolve\backend\app\connectors\mock_evidence\test_speech.wav"
$synth.SetOutputToWaveFile($targetFile)
$synth.Speak("Hello, this is a test of the speech synthesizer for UniResolve.")
$synth.Dispose()
Write-Host "Audio file created at $targetFile"
