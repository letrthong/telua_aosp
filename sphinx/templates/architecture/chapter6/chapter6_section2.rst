6.2 Kiểm Thử Đơn Vị & Kỹ Thuật Mocking (Unit Testing & Mocking Frameworks)
------------------------------------------------------------------------------------------

Phần này hướng dẫn triển khai kiểm thử đơn vị (**Unit Testing**) và kỹ thuật giả lập thành phần phụ thuộc (**Mocking**) cho cả tầng Car Service Java và tầng Native HAL C++.

Kiểm Thử Đơn Vị Tầng Car Framework (JUnit 5 + Mockito)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Ở tầng Framework Android Automotive, các dependency nặng như `AudioControlHAL` hoặc `AudioManager` được giả lập bằng **Mockito** để kiểm tra logic định tuyến độc lập:

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
           // 1. Given: Media đang phát với mức gain 0dB
           int zoneId = 0;
           int mediaGroupId = 0;
           mCarAudioService.setGroupVolume(mediaGroupId, 100, 0);

           // 2. When: Ứng dụng Navigation yêu cầu quyền ưu tiên
           mCarAudioService.handleAudioFocusChange(zoneId, USAGE_ASSISTANCE_NAVIGATION_GUIDANCE);

           // 3. Then: Service phải ra lệnh cho HAL hạ âm lượng Media xuống tối thiểu -15dB
           verify(mMockHalWrapper, times(1)).setVolumeGroupGain(eq(zoneId), eq(mediaGroupId), anyInt());
           assertTrue("Media zone must be ducked", mCarAudioService.isZoneDucked(zoneId));
       }
   }

Kiểm Thử Đơn Vị Tầng Native C++ (Google Test + Google Mock)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Ở tầng Native C++ và HAL, bộ khung chuẩn là **Google Test (GTest)** kết hợp **GMock** để kiểm định việc định cấu hình bus âm thanh và xử lý lỗi:

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
       // 1. Given: DSP phần cứng ở trạng thái sẵn sàng
       MockDspDriver mockDsp;
       EXPECT_CALL(mockDsp, isDspReady()).WillOnce(Return(true));
       EXPECT_CALL(mockDsp, setHardwareGain(0, -6.0f)).WillOnce(Return(0));

       AudioControlHAL hal(&mockDsp);

       // 2. When: Gọi cấu hình gain cho bus 0
       int status = hal.setVolumeGroupGain(0, -6.0f);

       // 3. Then: Phải trả về mã thành công 0
       EXPECT_EQ(status, 0);
   }

Kỹ Thuật Tiêm Lỗi (Fault Injection & Edge Cases)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Để đảm bảo hệ thống đạt chuẩn an toàn **ISO 26262 ASIL**, bộ kiểm thử đơn vị phải bao phủ các ca biên (Edge Cases):

- **HAL Death Test**: Giả lập tình huống tiến trình HAL bị crash đột ngột trong khi gọi IPC để đảm bảo Service không bị ANR và có cơ chế phục hồi liên kết Binder.
- **Null / Negative Volume Inputs**: Kiểm tra xem các giá trị âm lượng bất thường (< 0 hoặc > 100) có bị chặn ngay tại tầng Facade hay không.
- **Concurrent Focus Requests**: Bắn đồng thời 50 yêu cầu Audio Focus từ nhiều thread khác nhau để xác nhận không xảy ra tình trạng Deadlock (khóa tương hỗ).
