6.2 Unit Testing & Mocking Frameworks
------------------------------------------------------------------------------------------

This section provides implementation guidelines for unit tests (**Unit Testing**) and dependency isolation (**Mocking**) across both Java/Kotlin Car Framework services and Native C++ HAL layers.

Car Framework Unit Testing (JUnit 5 + Mockito)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In the Android Automotive framework tier, heavy dependencies such as ``AudioControlHAL`` or ``AudioManager`` are isolated using **Mockito** to test arbitration logic independently:

.. code-block:: java

   package com.android.car.audio;

   import static org.mockito.Mockito.*;
   import static org.junit.Assert.*;

   import org.junit.Before;
   import org.junit.Test;
   import org.mockito.Mock;
   import org.mockito.MockitoAnnotations;

   public class CarAudioServiceUnitTest {

       @Mock
       private AudioControlWrapper mMockHalWrapper;

       private CarAudioService mCarAudioService;

       @Before
       public void setUp() {
           MockitoAnnotations.initMocks(this);
           mCarAudioService = new CarAudioService(mMockHalWrapper);
       }

       @Test
       public void testNavAlertTriggersDucking() {
           // 1. Given: Media playback is active at normal gain
           int zoneId = 0;
           int mediaGroupId = 0;
           mCarAudioService.setGroupVolume(mediaGroupId, 100, 0);

           // 2. When: Navigation application requests high-priority focus
           mCarAudioService.handleAudioFocusChange(zoneId, USAGE_ASSISTANCE_NAVIGATION_GUIDANCE);

           // 3. Then: Service must instruct HAL to duck media volume to -15dB
           verify(mMockHalWrapper, times(1)).setVolumeGroupGain(eq(zoneId), eq(mediaGroupId), anyInt());
           assertTrue("Media zone must be ducked", mCarAudioService.isZoneDucked(zoneId));
       }
   }

Native C++ HAL Unit Testing (Google Test + Google Mock)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For native C++ HAL components, **Google Test (GTest)** and **GMock** form the verification framework for validating audio bus configurations and error handling:

.. code-block:: cpp

   #include <gtest/gtest.h>
   #include <gmock/gmock.h>
   #include "AudioControlHAL.h"

   using ::testing::Return;
   using ::testing::_;

   class MockDspDriver {
   public:
       MOCK_METHOD(int, setHardwareGain, (int busId, float gainDb), ());
       MOCK_METHOD(bool, isDspReady, (), ());
   };

   TEST(AudioControlHalTest, RouteBusAppliesCorrectGain) {
       // 1. Given: DSP hardware driver reports ready state
       MockDspDriver mockDsp;
       EXPECT_CALL(mockDsp, isDspReady()).WillOnce(Return(true));
       EXPECT_CALL(mockDsp, setHardwareGain(0, -6.0f)).WillOnce(Return(0));

       AudioControlHAL hal(&mockDsp);

       // 2. When: Configure gain index for physical bus 0
       int status = hal.setVolumeGroupGain(0, -6.0f);

       // 3. Then: Returns success status code 0
       EXPECT_EQ(status, 0);
   }

Fault Injection & Edge Case Testing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To ensure compliance with automotive functional safety standards (**ISO 26262 ASIL**), unit test suites must exercise corner cases:

- **HAL Crash & Death Recipient Tests**: Simulate unexpected vendor HAL process termination during active Binder IPC calls to ensure the Car Service gracefully attempts reconnection without hanging.
- **Out-of-Bounds Volume Boundary Tests**: Verify that abnormal volume inputs (< 0 or > 100) are rejected at the facade interface before reaching hardware registers.
- **High-Concurrency Race Condition Tests**: Dispatch 50 concurrent focus requests from multiple threads simultaneously to verify deadlock-free thread synchronization.
