rm -rf ~/.sensenova-claw
bash install/install.sh --dev
export SENSENOVA_CLAW_DEBUG_LLM=1
sensenova-claw run

