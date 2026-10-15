# Reflection (≤1 page)

Fill this in before you submit

**Which fault types were hardest to catch, and why?**

Mình thấy khó nhất là những lỗi có mức thay đổi nhỏ, đặc biệt ở luồng dữ liệu đơn hàng và các luồng feature, embedding, vì một chỉ số có thể vẫn nằm trong giới hạn cho phép nhưng khi nhiều chỉ số cùng lệch thì dữ liệu đã có dấu hiệu bất thường

Với dữ liệu đơn hàngkiểm tra riêng số hàng, tỷ lệ null, giá trị trung bình và độ trễ, sau đó kết hợp các chỉ số để phát hiện những trường hợp lệch đồng thời; với feature và embedding, mình chọn ngưỡng theo khoảng dao động bình thường được đề bài mô tả để hạn chế cảnh báo nhầm

Các lỗi contract và lineage dễ xác định hơn vì có điều kiện rõ ràng như vi phạm kiểu dữ liệu, vượt SLA, thiếu bảng đầu vào hoặc đầu ra không có downstream, tuy vậy mình vẫn phải kiểm tra đủ từng trường hợp để tránh bỏ sót

**What would you change about your cost/coverage tradeoff, if you had another pass?**

Mình gọi một công cụ phù hợp cho mỗi sự kiện để có đủ thông tin trước khi đưa ra quyết định; ở Public, chi phí là 240/220 credits, mình chấp nhận phần điểm bị trừ do vượt ngân sách vì bỏ qua công cụ có thể khiến nhiều lỗi không được phát hiện

Kết quả Practice đạt 50 điểm, Public đạt 46,90 điểm và Private đạt 32,41 điểm, cả ba phase đều không có cảnh báo nhầm, nhưng tỷ lệ phát hiện ở Private chỉ đạt khoảng 64,81%, cho thấy giải pháp vẫn còn bỏ sót những lỗi gần với dữ liệu bình thường

Nếu làm lại sẽ tập trung cải thiện khả năng nhận ra lỗi nhỏ và kiểm chứng trên dữ liệu độc lập, thay vì chỉ hạ ngưỡng để cố bắt thêm lỗi vì cách đó có thể làm tăng cảnh báo nhầm

**Nếu có thêm thời gian, bạn sẽ cải tiến cơ chế thống kê nào trong ctx.state?**

Mình sẽ lưu thống kê của các sự kiện gần nhất trong `ctx.state` để theo dõi xu hướng và nhận ra những thay đổi nhỏ kéo dài, chẳng hạn dùng trung bình trượt để so sánh dữ liệu mới với các đợt trước, đồng thời tránh cập nhật mốc tham chiếu từ những sự kiện đang có dấu hiệu lỗi
