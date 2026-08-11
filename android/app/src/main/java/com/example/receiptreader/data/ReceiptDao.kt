package com.example.receiptreader.data

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface ReceiptDao {

    /** 저장된 내역 (최근 저장 순). Flow 라 저장/삭제 시 화면이 자동 갱신됩니다. */
    @Query("SELECT * FROM receipts ORDER BY savedAt DESC")
    fun observeAll(): Flow<List<ReceiptEntity>>

    /** 전체 지출 합계 */
    @Query("SELECT COALESCE(SUM(total), 0) FROM receipts")
    fun observeTotalSum(): Flow<Int>

    @Insert
    suspend fun insert(receipt: ReceiptEntity): Long

    @Delete
    suspend fun delete(receipt: ReceiptEntity)
}
