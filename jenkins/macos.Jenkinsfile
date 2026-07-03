pipeline {
  agent { label 'macos' }

  environment {
    PYTHONUNBUFFERED = '1'
  }

  stages {
    stage('Checkout') {
      steps {
        checkout scm
      }
    }

    stage('Python Syntax') {
      steps {
        sh '''
          python3 -m py_compile \
            camera-core/src/akvc/runtime.py \
            camera-core/src/akvc/core/frame_input.py \
            camera-core/src/akvc/platforms/macos/installer.py \
            camera-core/src/akvc/platforms/macos/virtual_camera.py \
            tools/macos_native_verify.py \
            tools/macos_status_binary_check.py \
            tools/macos_list_devices_binary_check.py \
            tools/macos_smoke.py \
            tools/macos_install_session.py \
            tools/macos_benchmark.py \
            tools/macos_app_matrix_contract.py \
            tools/macos_build_contract.py \
            tools/macos_capability_contract.py \
            tools/macos_ci_artifact_contract.py \
            tools/macos_delivery_gate_contract.py \
            tools/macos_distribution_contract.py \
            tools/macos_topology_contract.py \
            tools/macos_readiness_contract.py \
            tools/macos_status_contract.py \
            tools/macos_validation_session_artifact_check.py \
            tools/macos_validation_session_acceptance.py \
            tools/macos_validation_session_acceptance_contract.py \
            tools/macos_validation_session_summary.py \
            tools/macos_validation_session_summary_contract.py \
            tools/macos_validation_session_contract.py \
            tools/macos_framebus_contract.py \
            tools/macos_input_contract.py \
            tools/macos_release_diagnostics.py \
            tools/macos_entrypoints_contract.py \
            tools/macos_sdk_contract.py \
            tools/macos_signing_pipeline_contract.py \
            tools/macos_stream_contract.py \
            tools/macos_framebus_roundtrip.py \
            tools/macos_toolchain_preflight.py \
            tools/macos_validation_report.py \
            tools/pyside6_virtual_camera_demo.py \
            tools/macos_validation_session.py \
            tools/make.py
          bash -n installer/macos/build_pkg.sh
          bash -n installer/macos/build_dmg.sh
          bash -n installer/macos/build_zip.sh
          bash -n installer/macos/sign_app.sh
          bash -n installer/macos/notarize.sh
          bash -n installer/macos/staple.sh
          bash -n installer/macos/uninstall.sh
        '''
      }
    }

    stage('Python Unit Tests') {
      steps {
        sh '''
          python3 -m pip install --upgrade pip
          python3 -m pip install pytest numpy opencv-python-headless
          python3 -m pip install -e camera-core
          python3 -m pytest -q \
            tests/unit/test_runtime.py \
            tests/unit/test_frame_input.py \
            tests/unit/test_pyside6_integration.py \
            tests/unit/test_sdk_virtual_camera.py \
            tests/unit/test_macos_installer.py \
            tests/unit/test_macos_virtual_camera.py \
            tests/unit/test_macos_ipc.py \
            tests/unit/test_package_lazy_imports.py \
            tests/unit/test_macos_install_result_api.py \
            tests/unit/test_cli_macos_install.py \
            tests/unit/test_desktop_macos_install_status.py \
            tests/unit/test_desktop_main_window.py \
            tests/unit/test_frame_sink_protocol.py \
            tests/unit/test_macos_shm_sink.py \
            tests/unit/test_macos_native_skeleton.py \
            tests/unit/test_macos_native_verify_tool.py \
            tests/unit/test_macos_status_binary_check_tool.py \
            tests/unit/test_macos_list_devices_binary_check_tool.py \
            tests/unit/test_macos_packaging_scripts.py \
            tests/unit/test_macos_signing_scripts.py \
            tests/unit/test_macos_uninstall_script.py \
            tests/unit/test_macos_runtime_sync.py \
            tests/unit/test_macos_smoke_tool.py \
            tests/unit/test_macos_install_session_tool.py \
            tests/unit/test_macos_make_tool_wrappers.py \
            tests/unit/test_macos_benchmark_tool.py \
            tests/unit/test_macos_app_matrix_contract_tool.py \
            tests/unit/test_macos_build_contract_tool.py \
            tests/unit/test_macos_capability_contract_tool.py \
            tests/unit/test_macos_ci_artifact_contract_tool.py \
            tests/unit/test_macos_delivery_gate_contract_tool.py \
            tests/unit/test_macos_distribution_contract_tool.py \
            tests/unit/test_macos_topology_contract_tool.py \
            tests/unit/test_macos_readiness_contract_tool.py \
            tests/unit/test_macos_status_contract_tool.py \
            tests/unit/test_macos_validation_session_artifact_check_tool.py \
            tests/unit/test_macos_validation_session_acceptance_tool.py \
            tests/unit/test_macos_validation_session_acceptance_contract_tool.py \
            tests/unit/test_macos_validation_session_summary_tool.py \
            tests/unit/test_macos_validation_session_summary_contract_tool.py \
            tests/unit/test_macos_validation_session_contract_tool.py \
            tests/unit/test_macos_framebus_contract_tool.py \
            tests/unit/test_macos_input_contract_tool.py \
            tests/unit/test_macos_release_diagnostics_tool.py \
            tests/unit/test_macos_framebus_roundtrip_tool.py \
            tests/unit/test_macos_entrypoints_contract_tool.py \
            tests/unit/test_macos_sdk_contract_tool.py \
            tests/unit/test_macos_signing_pipeline_contract_tool.py \
            tests/unit/test_macos_stream_contract_tool.py \
            tests/unit/test_macos_toolchain_preflight_tool.py \
            tests/unit/test_macos_validation_report_tool.py \
            tests/unit/test_pyside6_demo_tool.py \
            tests/unit/test_macos_validation_session_tool.py \
            tests/unit/test_macos_release_skeleton.py
        '''
      }
    }

    stage('Generate Xcode Project') {
      steps {
        sh '''
          brew list xcodegen >/dev/null 2>&1 || brew install xcodegen
          cd virtualcam/macos
          xcodegen generate --spec project.yml
        '''
      }
    }

    stage('Verify Native Sources') {
      steps {
        sh '''
          python3 tools/make.py preflight
          python3 tools/make.py release-diagnostics
          python3 tools/make.py verify-native
        '''
      }
    }

    stage('Benchmark Producer Path') {
      steps {
        sh '''
          python3 tools/macos_benchmark.py --width 1280 --height 720 --fps 30 --duration 1 --warmup 0 --output build/macos/benchmark.json
        '''
      }
    }

    stage('FrameBus Roundtrip') {
      steps {
        sh '''
          python3 tools/make.py framebus-roundtrip --width 64 --height 36 --output build/macos/framebus-roundtrip.json
        '''
      }
    }

    stage('Build Native Skeleton') {
      steps {
        sh '''
          python3 tools/make.py build
        '''
      }
    }

    stage('Check Built Status Binary') {
      steps {
        sh '''
          mkdir -p build/macos/session
          python3 tools/macos_status_binary_check.py \
            --status-tool build/macos/Build/Products/Release/akvc-macos-status \
            --output build/macos/session/status-binary-check.json
        '''
      }
    }

    stage('Check Built List-Devices Binary') {
      steps {
        sh '''
          python3 tools/make.py list-devices-binary-check \
            --list-devices-tool build/macos/Build/Products/Release/akvc-macos-list-devices \
            --output build/macos/session/list-devices-binary-check.json
        '''
      }
    }

    stage('Package macOS Artifacts') {
      steps {
        sh '''
          python3 tools/make.py package --skip-build --sync-runtime
        '''
      }
    }

    stage('Validation Session') {
      steps {
        sh '''
          python3 tools/make.py validation-session \
            --output-dir build/macos/session \
            --run-status-binary-check \
            --run-list-devices-binary-check \
            --skip-demo \
            --skip-benchmark \
            --status-tool build/macos/Build/Products/Release/akvc-macos-status \
            --list-devices-tool build/macos/Build/Products/Release/akvc-macos-list-devices
          python3 tools/make.py validation-session-artifact-check \
            --manifest build/macos/session/session-manifest.json \
            --require-existing-artifacts \
            --output build/macos/session/session-manifest-check.json
          python3 tools/make.py validation-session-summary \
            --manifest build/macos/session/session-manifest.json \
            --output build/macos/session/session-summary.md
          python3 tools/make.py validation-session-acceptance-contract \
            --output build/macos/session/session-acceptance-contract.json
        '''
      }
    }
  }

  post {
    always {
      archiveArtifacts artifacts: 'build/macos/VirtualCamera.pkg,build/macos/VirtualCamera.dmg,build/macos/VirtualCamera.zip,build/macos/benchmark.json,camera-core/src/akvc/_runtime/macos/VirtualCamera.pkg,camera-core/src/akvc/_runtime/macos/akvc-macos-status,camera-core/src/akvc/_runtime/macos/akvc-macos-install,camera-core/src/akvc/_runtime/macos/akvc-macos-uninstall,camera-core/src/akvc/_runtime/macos/akvc-macos-list-devices,camera-core/src/akvc/_runtime/macos/akvc-macos-sync-ipc,build/macos/framebus-roundtrip.json,build/macos/session/preflight.json,build/macos/session/release-diagnostics.json,build/macos/session/status-binary-check.json,build/macos/session/list-devices-binary-check.json,build/macos/session/entrypoints-contract.json,build/macos/session/install-session-report.json,build/macos/session/smoke-report.json,build/macos/session/session-manifest.json,build/macos/session/session-manifest-check.json,build/macos/session/session-acceptance.json,build/macos/session/session-acceptance-contract.json,build/macos/session/session-summary.md,build/macos/session/manual-results.template.json,build/macos/session/validation-report.json', allowEmptyArchive: true
    }
  }
}
